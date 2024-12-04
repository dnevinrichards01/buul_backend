FROM python:3.12.5-bullseye
SHELL ["/bin/bash", "--login", "-c"]
ARG USER_ID=1000
ARG GROUP_ID=1000
RUN groupadd -g $USER_ID -o app
RUN useradd -m -u $USER_ID -g $GROUP_ID -o -s /bin/bash app
ENV PIP_NO_CACHE_DIR off
ENV PIP_DISABLE_PIP_VERSION_CHECK on
ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1
ENV COLUMNS 80
RUN apt-get update \
 && apt-get install -y --force-yes \
 curl nano python3-pip gettext chrpath libssl-dev libxft-dev netcat \
 libfreetype6 libfreetype6-dev  libfontconfig1 libfontconfig1-dev \
  && rm -rf /var/lib/apt/lists/*
WORKDIR /code/
COPY requirements.txt /code/
RUN pip install wheel
RUN pip install -r requirements.txt
COPY . /code/
WORKDIR /code/
RUN chmod +x docker-setup.sh
USER app
