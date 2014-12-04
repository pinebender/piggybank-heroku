import os
from datetime import timedelta
from celery.schedules import crontab
#CSRF Enable
CSRF_ENABLED = True

#temporary dev key 
SECRET_KEY = '393jfj39fjfj93jflallalal' 

#csrf time limit
TIME_LIMIT = 86400


#sqlalchemy database config for heroku
if os.environ.get('DATABASE_URL') is None:
	SQLALCHEMY_DATABASE_URI = "postgresql:///" + os.path.join(basedir, 'app.db')
else:
	SQLALCHEMY_DATABASE_URI = os.environ['DATABASE_URL']

#celery config
BROKER_URL = 'amqp://guest@localhost:5672//'
BROKER_VHOST = '/'
CELERY_RESULT_BACKEND = 'amqp://guest@localhost:5672//'
CELERY_ALWAYS_EAGER = False
CELERYBEAT_SCHEDULE = {
    'pay-allowances': {
        'task': 'app.pay_allowances',
        'schedule': crontab(minute=0, hour=0),   #or timedelta(days=1)
        'args': ()
    	},
	}

CELERY_TIMEZONE = 'UTC'