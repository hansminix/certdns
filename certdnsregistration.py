#! /usr/bin/env python3
from datetime import datetime,timedelta
import sys
import logging
import logging.config
from configparser import RawConfigParser
from infoblox_client import connector
from infoblox_client.exceptions import InfobloxCannotCreateObject
from infoblox_client import objects
from urllib3 import disable_warnings
disable_warnings()
import sqlite3
import paramiko
import re
import pandas as pd

class CertDNSRegistration():
    
    def __init__(self, config):
        """
        Initaliseer object met Infoblox connectie
        """
        #Initialize logger
        self.logger = logging.getLogger(__name__)
        #Get configuration data
        self.config=config
        ibuser=config.get('Infoblox','ibuser')
        ibpassword=config.get('Infoblox','ibpassword')
        ibhost=config.get('Infoblox', 'ibhost')
        self.dnsview=config.get('Infoblox','dnsview')
        self.db=config.get("Infoblox", "sqlitedb")
        self.dateformat=config.get('Infoblox','dateformat')
        #Initialize Infoblox connection
        ibwapi=self.config.get('Infoblox', 'ibwapi')
        opts = {'host': ibhost, 'username': ibuser, 'password': ibpassword, 'http_request_timeout': 100, 'wapi_version': ibwapi }
        try:
            self.conn = connector.Connector(opts)
            testnet=self.conn.get_object('network',{'network':'10.0.0.0/8'})
        except Exception as e:
            self.logger.error(f"Error connecting to Infoblox: {e}")
            sys.exit(1)
        self.logger.debug(f"Infoblox login succesful.")

    def checkDNS(self, record, requestid):
        """
        Gebruik DNS om te controleren of het record bestaat, en of het een CName is. Dit wordt op een remote server in IEGI gedaan.
        """
        oput=None
        try:
            cli = paramiko.client.SSHClient()
            cli.set_missing_host_key_policy(paramiko.client.AutoAddPolicy())
            cli.connect(hostname=self.config.get('Infoblox','sshremote'), username=self.config.get('Infoblox','sshuser'), key_filename=self.config.get('Infoblox','sshkey'))
            chkcmd=f"dig {self.config.get('Infoblox','DNSserver')} +short {record}"
            stdin_, stdout_, stderr_ = cli.exec_command(chkcmd)
            oput=stdout_.readlines()
        except Exception as e:
            self.logger.error(f"Error connecting to server for DNS check: {e}")
            #Return error in first field + two empty vars
            return 'Fout bij DNS check, check logs.','',''
        finally:
            if cli:
                cli.close()
        #Check if output, then check if IP address.
        if oput:
            restr='^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
            for i in range(0,len(oput)):
                if re.match(restr,oput[i].strip()):
                    #First entry an IP address, it is an a-record, return arec, ip address and empty string
                    if i==0:
                        return 'arec',oput[i].strip(),''
                    else:
                        #Skip possible intermediate CNAME records, return cname, ip address and canonical name of original cname
                        return 'cname',oput[i].strip(), oput[0].strip()
            #No a-record or IP address related to cname, log error
            #Return error in first field + two empty vars
            return "Geen record kunnen maken, check handmatig", '', ''
        else:
            #return norec, possible internal DNS, so no output for DNS request
            return 'norec', '', ''
                
    def createTXTRecord(self, host, code, requestid):
        """
        Create text record, return value if succes, else retun None
        """
        try:
            txtrec=self.conn.create_object('record:txt', {'name': host, 'text': code, 'view': self.dnsview, 'extattrs':{'Task nr': {'value': 'Created by certdns script'}}})
        except Exception as e:
            self.logger.error(f"Error while trying to create TXT record for {host}: {e}")
            return 'Fout bij aanmaken TXT record, check logs.'
        return 'OK'
    
    def createCNameTXT(self, host, code, ipadd, requestid):
        """
        Delete the existing CName, and create an A record with the IP address found, then create TXT record
        """
        try:
            cnamefnd=self.conn.get_object('record:cname', {'name':host, 'view': self.dnsview})
            if cnamefnd:
                cnamedel=self.conn.delete_object(cnamefnd[0]['_ref'])
                print(cnamedel)
                if cnamedel:
                    arec=self.conn.create_object('record:a', {'name': host, 'ipv4addr': ipadd, 'view': self.dnsview, 'extattrs':{'Task nr': {'value': 'Created by certdns script'}}})
                    print(arec)
                    if arec:
                        txtrec=self.conn.create_object('record:txt', {'name': host, 'text': code, 'view': self.dnsview, 'extattrs':{'Task nr': {'value': 'Created by certdns script'}}})
                        return 'OK'
        except Exception as e:
            self.logger.error(f"Error while trying to create TXT record for {host}: {e}")
            return 'Fout bij aanmaken TXT record i.p.v. CNAME, check logs.'
        
    def getDataFromSqlite(self, fldlist, getcmd):
        #for every type create a fldlist to create dictionary with names and data from query, so a name can be used to access the data
        try:
            con=sqlite3.connect(self.db)
            cur=con.cursor()
            res=cur.execute(getcmd)
            processdata=res.fetchall()
            retdata=[]
            for entry in processdata:
                tlist = {fldlist[i]: entry[i] for i in range(len(fldlist))}
                retdata.append(tlist)            
            con.close()
        except Exception as e:
            self.logger.error(f"Error while trying to read data from database: {e}")
            return None
        self.logger.debug(f"SQLite data: { retdata }")
        return retdata
    
    def updateSqliteTable(self, table, id, fldlist):
        """
        Script om een rij bij te werken, input is dataframe van een rij
        """
        try:
            con=sqlite3.connect(self.db)
            cur=con.cursor()
            #Zet de lijst met velden om in string voor sql commando, verwijder laatste komma
            update_string = ''
            for col in fldlist:
                if fldlist[col].values[0]:
                    if type(fldlist[col].values[0] == str):
                        update_string += f'''{col}='{fldlist[col].values[0]}','''
                    else:
                        update_string += f'''{col}={fldlist[col].values[0]},'''
            upd_table=f"update { table } set {update_string[:-1]} where id = { id }"
            self.logger.debug(f"Update command: { upd_table }")
            cur.execute(upd_table)
            con.commit()
            cur.close()
        except Exception as e:
            self.logger.error(f"Error while trying to write data to database { table }: {e}")
        finally:
            if con:
                con.close()
    
    def processNewRequests(self):
        """
        Function to read all new requests and create TXT records. If error, check if there is a CName, and run processNewCName
        """
        #import data without date_set into pandas dataframe
        dbcon=sqlite3.connect(self.db)
        certs=pd.read_sql_query('select * from cert_dns where (date_set is null)',dbcon,index_col='id')
        dbcon.close()
        #getcmd=f"SELECT { ','.join(fldlist) } FROM cert_dns where (date_set is null)"
        #certs=self.getDataFromSqlite(fldlist=fldlist, getcmd=getcmd)
        for index, row in certs.iterrows():
            self.logger.debug(f"Processing new request: {row['certificatename']}")
            chrec, ipadd, oldcname = self.checkDNS(row['certificatename'], requestid=index)
            if chrec == 'arec'or chrec == 'norec':
                txtrec=self.createTXTRecord(host=row['certificatename'],code=row['hexcode'], requestid=index)
                if txtrec=='OK':
                    row['date_set']=datetime.now()
            elif chrec == 'cname':
                #cname, remove . (dot) at the end of the cname returned
                txtrec=self.createCNameTXT(host=row['certificatename'],code=row['hexcode'],ipadd=ipadd, requestid=index)
                row['date_set']=datetime.now()
                if txtrec=='OK':
                    row['cname']=oldcname[:-1]
                else:
                    row['errors']=txtrec
            else:
                row['errors']=chrec
            self.updateSqliteTable(table='cert_dns', id=index,fldlist=certs.loc[[index]])

    def processOldRequests(self):
        """
        Function to read all processed requests without errors. Check if TXT record has been accessed, if so, delete it, and recreate the CNAME if necessary
        """
        #import data without date_set into pandas dataframe
        dbcon=sqlite3.connect(self.db)
        certs=pd.read_sql_query('select * from cert_dns where (date_set is not null and date_reset is null and errors is null)',dbcon,index_col='id')
        dbcon.close()
        for index, row in certs.iterrows():
            self.logger.debug(f"Processing old request: {row['certificatename']}")
            #First check if TXT record has been requested
            try:
                txtrec=self.conn.get_object('record:txt', {'name':row['certificatename'], 'view': self.dnsview},return_fields=['name','last_queried'])
                self.logger.debug(f"Found text record: {txtrec}")
                if txtrec:
                    if 'last_queried' in txtrec[0] or (datetime.now() - datetime.strptime(row['date_set'],self.dateformat)).days > 7:
                        self.logger.debug(f"Found record to process: { row['certificatename']}.")
                        if row['cname']:
                            #Delete TXT record
                            txtdel=self.conn.delete_object(txtrec[0]['_ref'])
                            self.logger.debug(f"Deleted record {txtdel}")
                            #Delete A-record
                            arec=self.conn.get_object('record:a',{'name':row['certificatename'], 'view': self.dnsview})
                            if arec:
                                adel=self.conn.delete_object(arec[0]['_ref'])
                                self.logger.debug(f"Deleted record {adel}")
                            cnamerec=self.conn.create_object('record:cname',{'name': row['certificatename'], 'canonical': row['cname'], 'view': self.dnsview})
                            self.logger.debug(f"Created record {cnamerec}")
                        else:
                            txtdel=self.conn.delete_object(txtrec[0]['_ref'])
                            self.logger.debug(f"Deleted record {txtdel}")
                        row['date_reset']=datetime.now()
                    if (datetime.now() - datetime.strptime(row['date_set'],self.dateformat)).days > 7:
                        row['errors']='TXT record niet opgevraagd in laatste 7 dagen, request teruggedraaid'
                else:
                    row['errors']='Geen TXT record gevonden, controleer handmatig'
            except Exception as e:
                row['date_set']=datetime.now()
                row['errors']='Fout bij wissen TXT record, check logs.'
                self.logger.error(f"Error while trying to read and delete TXT record for {row['certificatename']}: {e}")
            self.updateSqliteTable(table='cert_dns', id=index, fldlist=certs.loc[[index]])

def main():
    #Now read config file, log error if it fails
    config = RawConfigParser()
    try:
        config.read('CertDNSRegistration.conf')
    except Exception as e:
        print(f"Error while reading configuration file CertDNSRegistration.conf: {e}")
        sys.exit(1)
    
    #Declare a logger, and initialze it from the configuration file
    logging.config.fileConfig('logging.config')
    logger = logging.getLogger(__name__)
    logger.info("Start certdns script")
    cdr=CertDNSRegistration(config=config)
    cdr.processNewRequests()
    cdr.processOldRequests()
    
if __name__ == '__main__':
    main()        