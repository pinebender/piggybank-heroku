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

BROKER_URL=os.environ['CLOUDAMQP_URL'] 
BROKER_VHOST = '/'
CELERY_RESULT_BACKEND=os.environ['CLOUDAMQP_URL']
CELERY_ALWAYS_EAGER = False
CELERYBEAT_SCHEDULE = {
    'pay-allowances': {
        'task': 'app.pay_allowances',
        'schedule': crontab(minute=0, hour=0),   #or timedelta(days=1)
        'args': ()
    	},
	}
BROKER_POOL_LIMIT = 1

CELERY_TIMEZONE = 'UTC'
