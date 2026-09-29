FROM ubuntu:26.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive

# Update and install necessary packages, including python3-pip
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    cron \
    curl \
    nano \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgtk-3-0t64 \
    libdbus-glib-1-2 \
    libgdk-pixbuf-2.0-0 \
    libxt6t64 \
    libnss3 \
    libnspr4 \
    tar \
    fonts-dejavu-core \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Install necessary dependencies
RUN apt-get update && apt-get install -y \
    wget \
    tar \
    libx11-xcb1 \
    libxcomposite1 \
    libasound2t64 \
    libgdk-pixbuf-2.0-0 \
    curl \
    ca-certificates

# Install rsyslog for logging
RUN apt-get update && apt-get install -y rsyslog
RUN echo "cron.* /var/log/cron.log" >> /etc/rsyslog.d/50-default.conf

# Download the latest Firefox
RUN wget -O /tmp/firefox.tar.xz "https://download.mozilla.org/?product=firefox-latest&os=linux64&lang=en-US" && \
    tar -xJf /tmp/firefox.tar.xz -C /opt && \
    ln -s /opt/firefox/firefox /usr/local/bin/firefox && \
    rm /tmp/firefox.tar.xz

# Ubuntu >= 23.04 blocks system-wide pip installs (PEP 668), so use a virtualenv.
# It is first in PATH, so "python3"/"pip3" resolve to the venv from here on.
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip3 install --upgrade pip && \
    pip3 install selenium

# Copy your local geckodriver to the container
COPY src/files/geckodriver-v0.35.0-linux64.tar.gz /tmp/

# Extract the geckodriver and move it to /usr/local/bin
RUN tar -xzvf /tmp/geckodriver-v0.35.0-linux64.tar.gz -C /tmp && \
    mv /tmp/geckodriver /usr/local/bin/ && \
    rm /tmp/geckodriver-v0.35.0-linux64.tar.gz

# Set the working directory
WORKDIR /app

# Copy application code
COPY src/requirements.txt ./
COPY src/nsm.py ./
COPY src/pocket-ersatz.py ./
COPY src/pocket-mailer.py ./
COPY src/pocket-mailer-epub.py ./
COPY src/app.py /app/
COPY src/templates/ /app/templates/

# Copy custom Firefox extensions into the container
COPY src/files/istilldontcareaboutcookies-1.1.4.xpi ./
COPY src/files/bypass-paywalls-firefox.xpi ./

# Copy custom Firefox extensions into the browser extensions directory
RUN mkdir -p /usr/lib/firefox/browser/extensions/ \
    && cp /app/istilldontcareaboutcookies-1.1.4.xpi /usr/lib/firefox/browser/extensions/ \
    && cp /app/bypass-paywalls-firefox.xpi /usr/lib/firefox/browser/extensions/

# Create persistent storage directory
RUN mkdir -p /app/data && chmod 777 /app/data

# Copy default config files into persistent storage
COPY src/config.cfg /app/data/
COPY src/urls.tsv /app/data/
COPY src/feeds.cfg /app/data/
COPY src/filter.txt /app/data/
COPY src/killfile.txt /app/data/

# Declare persistent volume
VOLUME ["/app/data"]

# Install Python dependencies (including Flask)
RUN pip3 install --no-cache-dir -r requirements.txt \
    && pip3 install Flask


# Install cron
RUN apt-get update && apt-get install -y cron

# Copy your cron jobs to /etc/cron.d/
COPY crontab.txt /etc/cron.d/myjobs
RUN chmod 0644 /etc/cron.d/myjobs

# Create startup script to run cron and Flask app
RUN echo '#!/bin/bash\n\
python3 /app/app.py &\n\
exec cron -f' > /start.sh && chmod +x /start.sh

# tini als PID 1 räumt verwaiste Prozesse (z.B. Firefox-Kinder) ab
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/start.sh"]


