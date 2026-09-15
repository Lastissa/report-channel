import os
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

AUTH_USER_MODEL = "AUTHENTICATION.Auth"

BASE_DIR = Path(__file__).resolve().parent.parent

CSRF_FAILURE_VIEW = "AUTHENTICATION.views.csrf_failure"
CSRF_TRUSTED_ORIGINS = ['https://esta-sensate-unquickly.ngrok-free.dev',]

SECRET_KEY = os.getenv('DJANGO_SECRET') or "abcdef"

DEBUG = os.getenv("DEBUG") == "True" or False
# DEBUG = False

ALLOWED_HOSTS = (os.getenv("ALLOWED_HOSTS") or "localhost,127.0.0.1,testserver").split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    '_',
    'AUTHENTICATION',
    'BLOG',
    'HOME',
    'STAFF'
    
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    '_.middleware.MaintenanceModeMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'AUTHENTICATION.middleware.AuthEndpointThrottleMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'NoName.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'SERVICE_INTERNAL.config.custom_context_processors',
            ],
        },
    },
]

WSGI_APPLICATION = 'NoName.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


STATIC_URL = 'static/'


MAILERS = {
    'default': {
        'BACKEND': 'django.core.mail.backends.console.EmailBackend',
    },
}

STATIC_ROOT = "staticfiles/"

DOMAIN_NAME = os.getenv("DOMAIN_NAME") or "http://localhost:8000"

SY_SECRET = os.getenv('sy_secret')

MAINTENANCE_MODE = os.getenv('MAINTENANCE_MODE', "FALSE")

