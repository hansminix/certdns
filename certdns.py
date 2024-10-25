from app import create_app
import logging

logging.basicConfig(filename='error.log',level=logging.DEBUG)

app=create_app()

if __name__ == '__main__':
    app.config['FLASK_ENV'] = 'development'
    app.run(debug=True, host='0.0.0.0', port=5000)
    