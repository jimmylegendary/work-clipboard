# Dockerfile
FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    firefox-esr \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install GeckoDriver
RUN GECKODRIVER_VERSION=0.33.0 && \
    wget -O /tmp/geckodriver.tar.gz https://github.com/mozilla/geckodriver/releases/download/v${GECKODRIVER_VERSION}/geckodriver-v${GECKODRIVER_VERSION}-linux64.tar.gz && \
    tar -xzf /tmp/geckodriver.tar.gz -C /tmp && \
    mv /tmp/geckodriver /usr/local/bin/geckodriver && \
    chmod +x /usr/local/bin/geckodriver && \
    rm /tmp/geckodriver.tar.gz

# Install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application
COPY metabase_screenshot_service.py .

EXPOSE 5000
CMD ["python", "metabase_screenshot_service.py"]


# Check Firefox installation
firefox --version

# Check GeckoDriver installation
geckodriver --version

# Check Python packages
pip list | grep -E "(flask|selenium)"

# Test selenium with Firefox
python -c "
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
options = Options()
options.add_argument('--headless')
driver = webdriver.Firefox(options=options)
driver.get('https://www.google.com')
print('Firefox + Selenium working:', driver.title)
driver.quit()
"



#!/bin/bash
# setup.sh

echo "Installing Metabase Screenshot Service dependencies..."

# Update system
sudo apt-get update

# Install Firefox
sudo apt-get install -y firefox

# Install GeckoDriver
GECKODRIVER_VERSION="0.33.0"
wget -O /tmp/geckodriver.tar.gz https://github.com/mozilla/geckodriver/releases/download/v${GECKODRIVER_VERSION}/geckodriver-v${GECKODRIVER_VERSION}-linux64.tar.gz
tar -xzf /tmp/geckodriver.tar.gz -C /tmp
sudo mv /tmp/geckodriver /usr/local/bin/geckodriver
sudo chmod +x /usr/local/bin/geckodriver
rm /tmp/geckodriver.tar.gz

# Install Python dependencies
pip install -r requirements.txt

# Verify installation
echo "Verifying installation..."
firefox --version
geckodriver --version
python -c "import selenium; print('Selenium version:', selenium.__version__)"
python -c "import flask; print('Flask version:', flask.__version__)"

echo "Setup completed successfully!"
