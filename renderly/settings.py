import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
DEBUG = os.getenv('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'drf_spectacular',
    'video_generation',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'renderly.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'renderly.wsgi.application'

DB_CONN_MAX_AGE = int(os.getenv('DB_CONN_MAX_AGE', '600'))
DB_SSL_REQUIRE = os.getenv('DB_SSL_REQUIRE', 'False') == 'True'
RUN_TASK_INLINE = os.getenv('RUN_TASK_INLINE', 'False') == 'True'
PGHOST = os.getenv('PGHOST')
PGPORT = os.getenv('PGPORT', '5432')
PGUSER = os.getenv('PGUSER')
PGPASSWORD = os.getenv('PGPASSWORD')
PGDATABASE = os.getenv('PGDATABASE')

if PGHOST and PGUSER and PGPASSWORD and PGDATABASE:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': PGDATABASE,
            'USER': PGUSER,
            'PASSWORD': PGPASSWORD,
            'HOST': PGHOST,
            'PORT': PGPORT,
            'CONN_MAX_AGE': DB_CONN_MAX_AGE,
            'OPTIONS': {
                'sslmode': 'require' if DB_SSL_REQUIRE else 'prefer'
            }
        }
    }
else:
    DATABASES = {
        'default': dj_database_url.parse(
            os.getenv('DATABASE_URL', f'sqlite:///{BASE_DIR / "db.sqlite3"}'),
            conn_max_age=DB_CONN_MAX_AGE,
            ssl_require=DB_SSL_REQUIRE,
        )
    }

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'video_generation.auth.APIKeyAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID')
GCP_SERVICE_ACCOUNT_FILE = os.getenv('GCP_SERVICE_ACCOUNT_FILE')
GCS_BUCKET = os.getenv('GCS_BUCKET', 'bucket')

HEYGEN_API_KEY = os.getenv('HEYGEN_API_KEY')

CELERY_BROKER_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8080",
]

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {
        'video_generation': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Renderly API',
    'DESCRIPTION': 'Automated product video generation using Veo and HeyGen with job tracking, authentication, and webhooks.',
    'VERSION': '1.0.0',
    'SERVERS': [{'url': 'http://127.0.0.1:8001', 'description': 'Local'}],
    'COMPONENT_SPLIT_REQUEST': True,
    'SERVE_INCLUDE_SCHEMA': False,
    'CONTACT': {'name': 'Renderly Support', 'url': 'https://example.com/support', 'email': 'support@example.com'},
    'LICENSE': {'name': 'Proprietary', 'url': 'https://example.com/license'},
    'SECURITY': [{'ApiKey': []}],
    'SECURITY_SCHEMES': {
        'ApiKey': {
            'type': 'apiKey',
            'name': 'X-Api-Key',
            'in': 'header',
            'description': 'Provide your API key in X-Api-Key header',
        }
    },
    'TAGS': [
        {'name': 'Video Generation', 'description': 'Create product videos via Veo and HeyGen'},
        {'name': 'Jobs', 'description': 'Job status and listing'},
    ],
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': True,
        'filter': True,
        'tryItOutEnabled': True,
        'tagsSorter': 'alpha',
        'operationsSorter': 'alpha',
        'defaultModelExpandDepth': 1,
        'defaultModelsExpandDepth': 0,
        'docExpansion': 'none',
    },
}
