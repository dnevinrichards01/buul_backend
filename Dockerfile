FROM python:3.12.5-bullseye
SHELL ["/bin/bash", "--login", "-c"]
#ARG USER_ID=1000
#ARG GROUP_ID=1000
#RUN groupadd -g $USER_ID -o app
#RUN useradd -m -u $USER_ID -g $GROUP_ID -o -s /bin/bash app
ENV PIP_NO_CACHE_DIR off
ENV PIP_DISABLE_PIP_VERSION_CHECK on
ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1
ENV COLUMNS 80
RUN apt-get update && apt-get install -y \
 curl nano python3-pip gettext chrpath libssl-dev libxft-dev postgresql-client supervisor \
 libfreetype6 libfreetype6-dev libfontconfig1 libfontconfig1-dev sudo ufw systemd \
 python3-venv python3-dev libpq-dev postgresql postgresql-contrib nginx systemd-sysv \
 snapd \
  && rm -rf /var/lib/apt/lists/*
WORKDIR /code/
COPY requirements.txt /code/
RUN pip install wheel
COPY Dockerfile accumate_backend api entrypoint.sh manage.py \
 requirements.txt staticfiles /code/
RUN pip install -r requirements.txt
COPY conf_files/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY conf_files/nginx.conf /etc/nginx/nginx.conf
RUN mkdir /run/gunicorn/
RUN chown www-data: /var/log/ /var/log/nginx /var/lib/nginx /var/www/
RUN chown www-data: /etc/nginx /etc/nginx/conf.d /etc/nginx/nginx.conf
RUN chmod 755 /run
RUN chmod 777 /etc
RUN mkdir /etc/letsencrypt /etc/letsencrypt/live /etc/letsencrypt/live/accumate-backend.link/
COPY conf_files/fullchain.pem /etc/letsencrypt/live/accumate-backend.link/fullchain.pem
COPY conf_files/privkey.pem /etc/letsencrypt/live/accumate-backend.link/privkey.pem
RUN mkdir /run/nginx/
RUN chown www-data: /run/nginx/ /run/gunicorn/
USER www-data
CMD ["./entrypoint.sh"]