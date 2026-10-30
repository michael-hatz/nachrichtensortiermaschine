FROM ubuntu:26.04

ENV DEBIAN_FRONTEND=noninteractive
# Local timezone incl. DST (CET/CEST); cron schedules in local time
ENV TZ=Europe/Berlin

# Firefox and geckodriver are pinned together: a new Firefox may need a newer geckodriver.
# To update, bump both versions and their checksums (Firefox: SHA256SUMS next to the release,
# geckodriver: sha256sum of the downloaded tarball).
ARG FIREFOX_VERSION=153.4.0esr
ARG FIREFOX_SHA256=1832c20dd8c5f69cee933debe62372f5c997845413c8eff846317f6463172032
ARG GECKODRIVER_VERSION=0.37.1
ARG GECKODRIVER_SHA256=e815130ea95983e162ae91843b48d3a3ce991735635fce83a647afde21e09f7e

# System packages: Python, cron, tini, and the libraries Firefox needs
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    cron \
    curl \
    ca-certificates \
    xz-utils \
    tini \
    tzdata \
    procps \
    fonts-dejavu-core \
    libx11-6 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libxt6t64 \
    libgtk-3-0t64 \
    libdbus-glib-1-2 \
    libgdk-pixbuf-2.0-0 \
    libasound2t64 \
    libnss3 \
    libnspr4 \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# Firefox
RUN curl -fsSL -o /tmp/firefox.tar.xz \
        "https://ftp.mozilla.org/pub/firefox/releases/${FIREFOX_VERSION}/linux-x86_64/en-US/firefox-${FIREFOX_VERSION}.tar.xz" \
    && echo "${FIREFOX_SHA256}  /tmp/firefox.tar.xz" | sha256sum -c - \
    && tar -xJf /tmp/firefox.tar.xz -C /opt \
    && ln -s /opt/firefox/firefox /usr/local/bin/firefox \
    && rm /tmp/firefox.tar.xz

# geckodriver
RUN curl -fsSL -o /tmp/geckodriver.tar.gz \
        "https://github.com/mozilla/geckodriver/releases/download/v${GECKODRIVER_VERSION}/geckodriver-v${GECKODRIVER_VERSION}-linux64.tar.gz" \
    && echo "${GECKODRIVER_SHA256}  /tmp/geckodriver.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/geckodriver.tar.gz -C /usr/local/bin \
    && rm /tmp/geckodriver.tar.gz

# Unprivileged user for the cronjobs and scripts (Firefox opens arbitrary web pages)
RUN useradd --system --create-home --home-dir /home/nsm --shell /usr/sbin/nologin nsm

# Ubuntu >= 23.04 blocks system-wide pip installs (PEP 668), so use a virtualenv.
# It is first in PATH, so "python3"/"pip3" resolve to the venv from here on.
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Python dependencies before the code, so code changes don't reinstall them
COPY src/requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# Application code
COPY src/common.py src/feeddb.py src/nsm.py src/mailtext.py src/pocket-ersatz.py src/pocket-mailer.py \
     src/pocket-mailer-epub.py src/archive-sort.py src/readlater.py src/app.py ./
COPY src/templates/ /app/templates/

# Firefox extensions, loaded by pocket-ersatz.py via install_addon
COPY src/files/istilldontcareaboutcookies-1.1.4.xpi src/files/bypass-paywalls-firefox.xpi ./

# Default data files; the volume gets them on first use
COPY src/config.cfg src/feeds.cfg src/filter.txt src/killfile.txt /app/data/
RUN chown -R nsm:nsm /app/data && chmod 2775 /app/data
# Pristine copies; the web app restores them if the mounted volume lacks them
COPY src/config.cfg src/feeds.cfg src/filter.txt src/killfile.txt /app/defaults/
VOLUME ["/app/data"]

# Cron jobs
COPY crontab.txt /etc/cron.d/myjobs
RUN chmod 0644 /etc/cron.d/myjobs

# Startup script: permissions of /app/data, gunicorn and cron
COPY --chmod=755 start.sh /start.sh

EXPOSE 5000

# Healthy if the web interface answers (any HTTP status, it requires a login) and cron runs
HEALTHCHECK --interval=1m --timeout=10s --start-period=30s --retries=3 \
    CMD curl -s -o /dev/null http://127.0.0.1:5000/ && pgrep -x cron > /dev/null || exit 1

# tini als PID 1 räumt verwaiste Prozesse (z.B. Firefox-Kinder) ab
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/start.sh"]
