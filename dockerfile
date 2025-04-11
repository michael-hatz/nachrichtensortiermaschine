FROM ubuntu:22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive

# Update and install necessary packages, including python3-pip
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    cron \
    curl \
    nano \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    libxml2-dev \
    libxslt1-dev \
    libz-dev \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgtk-3-0 \
    libdbus-glib-1-2 \
    libgdk-pixbuf2.0-0 \
    libxt6 \
    libnss3 \
    libnspr4 \
    tar \
    sudo \
    pandoc \
    && rm -rf /var/lib/apt/lists/*

# Install necessary dependencies
RUN apt-get update && apt-get install -y \
    wget \
    tar \
    libx11-xcb1 \
    libxcomposite1 \
    libasound2 \
    libgdk-pixbuf2.0-0 \
    curl \
    ca-certificates

# Copy the local Firefox installer into the container
COPY src/files/firefox-134.0.2.tar.bz2 /tmp/firefox.tar.bz2

# Extract and install Firefox
RUN tar -xjf /tmp/firefox.tar.bz2 -C /opt && \
    ln -s /opt/firefox/firefox /usr/local/bin/firefox && \
    rm /tmp/firefox.tar.bz2

# Install pip3 and selenium separately in another RUN command to catch any potential errors
RUN python3 -m pip install --upgrade pip && \
    pip3 install selenium

# Copy your local geckodriver to the container
COPY src/files/geckodriver-v0.35.0-linux64.tar.gz /tmp/

# Extract the geckodriver and move it to /usr/local/bin
RUN tar -xzvf /tmp/geckodriver-v0.35.0-linux64.tar.gz -C /tmp && \
    sudo mv /tmp/geckodriver /usr/local/bin/ && \
    rm /tmp/geckodriver-v0.35.0-linux64.tar.gz

# Set the working directory
WORKDIR /app

# Copy application code
COPY src/requirements.txt ./
COPY src/nsm.py ./
COPY src/pocket-ersatz.py ./
COPY src/pocket-mailer.py ./
COPY src/pocket-mailer-epub.py ./

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

# Copy killfile.txt to the container
COPY src/killfile.txt /app/data/

# Declare persistent volume
VOLUME ["/app/data"]

# Install Python dependencies (including Flask)
RUN pip3 install --no-cache-dir -r requirements.txt \
    && pip3 install Flask

# Set up cron job to run nsm.py and pocket-ersatz.py every hour
RUN echo "35 * * * * /usr/bin/env python3 /app/nsm.py" > /etc/cron.d/nsm-cron \
    && echo "45 * * * * /usr/bin/env python3 /app/pocket-ersatz.py" >> /etc/cron.d/nsm-cron \
    && echo "27 05 * * * /usr/bin/env python3 /app/pocket-mailer.py >> /app/mailer.log 2>&1" >> /etc/cron.d/nsm-cron \
    && echo "0 04 * * * rm -r /tmp/*" >> /etc/cron.d/nsm-cron \
    && chmod 0644 /etc/cron.d/nsm-cron \
    && crontab /etc/cron.d/nsm-cron

# Copy Flask app and templates
COPY src/app.py /app/
COPY src/templates/ /app/templates/

# Expose the web interface port
EXPOSE 5000

# Start cron in the foreground and Flask app
CMD ["sh", "-c", "cron && python3 /app/app.py"]

