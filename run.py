# metabase_screenshot_service.py
from flask import Flask, request, jsonify, send_file
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import base64
import time
import io
from datetime import datetime
import logging
import socket
import random

# Configuration
METABASE_BASE_URL = "http://your-metabase.com"
DEFAULT_QUESTION_ID = "123"
DEFAULT_USERNAME = "your-username"
DEFAULT_PASSWORD = "your-password"

# Firefox debug port range
DEBUG_PORT_RANGE = (8030, 8049)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def find_available_port(start_port=8030, end_port=8049):
    """Find an available port in the specified range"""
    ports = list(range(start_port, end_port + 1))
    random.shuffle(ports)  # Randomize to avoid conflicts
    
    for port in ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                logger.info(f"Found available port: {port}")
                return port
        except OSError:
            continue
    
    logger.warning(f"No available ports found in range {start_port}-{end_port}")
    return None

class MetabaseScreenshotService:
    def __init__(self):
        logger.info("Initializing Metabase Screenshot Service")
        self.firefox_options = Options()
        self.firefox_options.add_argument("--headless")
        self.firefox_options.add_argument("--no-sandbox")
        self.firefox_options.add_argument("--disable-dev-shm-usage")
        self.firefox_options.add_argument("--width=1400")
        self.firefox_options.add_argument("--height=1000")
        
        # Set real browser User-Agent
        self.firefox_options.set_preference("general.useragent.override", 
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0")
        
        # Disable some security features that might interfere
        self.firefox_options.set_preference("security.tls.insecure_fallback_hosts", METABASE_BASE_URL.replace("http://", "").replace("https://", ""))
        self.firefox_options.set_preference("network.stricttransportsecurity.preloadlist", False)
        self.firefox_options.set_preference("security.tls.strict_fallback_hosts", METABASE_BASE_URL.replace("http://", "").replace("https://", ""))
        
        logger.info("Firefox options configured")
        
    def create_firefox_driver(self):
        """Create Firefox driver with available debug port"""
        debug_port = find_available_port(DEBUG_PORT_RANGE[0], DEBUG_PORT_RANGE[1])
        
        if debug_port:
            logger.info(f"Using debug port: {debug_port}")
            self.firefox_options.add_argument(f"--remote-debugging-port={debug_port}")
        else:
            logger.warning("No available debug port found, using default configuration")
        
        try:
            # Try to create driver with service
            service = Service()
            driver = webdriver.Firefox(service=service, options=self.firefox_options)
            logger.info("Firefox WebDriver initialized successfully")
            return driver
        except Exception as e:
            logger.error(f"Failed to create Firefox driver with service: {e}")
            try:
                # Fallback: try without service
                driver = webdriver.Firefox(options=self.firefox_options)
                logger.info("Firefox WebDriver initialized successfully (fallback method)")
                return driver
            except Exception as e2:
                logger.error(f"Failed to create Firefox driver (fallback): {e2}")
                raise
        
    def wait_for_dynamic_elements(self, driver, max_wait=30):
        """Wait for JavaScript dynamic rendering completion"""
        logger.info("Step 1/3: Waiting for dynamic content loading...")
        
        # 1. Wait for page load completion
        logger.info("  - Checking document ready state")
        try:
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            logger.info("  - Document ready state: complete")
        except TimeoutException:
            logger.warning("  - Document ready state timeout, continuing...")
        
        # 2. Additional wait for JavaScript execution
        logger.info("  - Waiting 5 seconds for JavaScript execution")
        time.sleep(5)
        
        # 3. Check login form existence with JavaScript
        logger.info("  - Searching for login form elements")
        wait_script = """
        return new Promise((resolve) => {
            let attempts = 0;
            const maxAttempts = 100;
            
            function checkForLoginForm() {
                attempts++;
                
                const selectors = [
                    'input[name="username"]',
                    'input[name="email"]', 
                    'input[type="text"]',
                    'input[type="email"]',
                    'input[placeholder*="username" i]',
                    'input[placeholder*="email" i]'
                ];
                
                for (let selector of selectors) {
                    const element = document.querySelector(selector);
                    if (element && element.offsetParent !== null) {
                        resolve({
                            found: true,
                            selector: selector,
                            attempts: attempts
                        });
                        return;
                    }
                }
                
                if (attempts < maxAttempts) {
                    setTimeout(checkForLoginForm, 300);
                } else {
                    resolve({found: false, attempts: attempts});
                }
            }
            
            checkForLoginForm();
        });
        """
        
        try:
            logger.info("  - Executing JavaScript form detection...")
            result = driver.execute_async_script(wait_script)
            if result.get("found"):
                logger.info(f"  - Login form found after {result.get('attempts', 0)} attempts")
                logger.info(f"  - Successful selector: {result.get('selector')}")
            else:
                logger.warning(f"  - Login form not found after {result.get('attempts', 0)} attempts")
            return result
        except Exception as e:
            logger.error(f"  - JavaScript execution error: {e}")
            return {"found": False, "error": str(e)}
    
    def login_to_metabase(self, driver, username, password):
        """Login to Metabase with dynamic rendering consideration"""
        login_url = f"{METABASE_BASE_URL}/auth/login"
        logger.info(f"Step 2/3: Starting login process")
        logger.info(f"  - Target URL: {login_url}")
        logger.info(f"  - Using debug port from driver capabilities")
        
        # Check current driver capabilities
        try:
            capabilities = driver.capabilities
            logger.info(f"  - Browser name: {capabilities.get('browserName', 'unknown')}")
            logger.info(f"  - Browser version: {capabilities.get('browserVersion', 'unknown')}")
        except Exception as e:
            logger.warning(f"  - Could not retrieve driver capabilities: {e}")
        
        try:
            logger.info("  - Attempting to load login page...")
            driver.get(login_url)
            logger.info(f"  - Page load request sent")
            
            # Check if page actually loaded
            current_url = driver.current_url
            page_title = driver.title
            logger.info(f"  - Current URL after load: {current_url}")
            logger.info(f"  - Page title: {page_title}")
            
            # Check if we got redirected or if there's an error
            if "error" in current_url.lower() or "404" in page_title or "not found" in page_title.lower():
                logger.error(f"  - Page load failed - got error page")
                logger.error(f"    URL: {current_url}")
                logger.error(f"    Title: {page_title}")
                return False
            
            # Check page source for error indicators
            try:
                page_source = driver.page_source
                if len(page_source) < 100:
                    logger.error(f"  - Page source too short ({len(page_source)} chars), possible load failure")
                    return False
                
                if "connection refused" in page_source.lower() or "unable to connect" in page_source.lower():
                    logger.error("  - Connection error detected in page source")
                    return False
                    
                logger.info(f"  - Page source length: {len(page_source)} characters")
            except Exception as e:
                logger.warning(f"  - Could not check page source: {e}")
            
            logger.info(f"  - Page loaded successfully")
            
        except Exception as e:
            logger.error(f"  - Failed to load login page: {e}")
            logger.error(f"  - Exception type: {type(e).__name__}")
            
            # Save screenshot for debugging
            try:
                driver.save_screenshot("page_load_error.png")
                logger.info("  - Error screenshot saved: page_load_error.png")
            except:
                logger.error("  - Could not save error screenshot")
            
            return False
        
        # Wait for dynamic elements loading
        logger.info("  - Waiting for dynamic form elements...")
        form_result = self.wait_for_dynamic_elements(driver)
        
        if not form_result.get("found"):
            logger.error("  - Login form not found after dynamic loading")
            
            # Additional debugging
            try:
                current_page_source = driver.page_source
                logger.info(f"  - Final page source length: {len(current_page_source)}")
                
                # Save page source for debugging
                with open("login_page_source.html", "w", encoding="utf-8") as f:
                    f.write(current_page_source)
                logger.info("  - Page source saved: login_page_source.html")
                
                driver.save_screenshot("login_form_not_found.png")
                logger.info("  - Screenshot saved: login_form_not_found.png")
            except Exception as e:
                logger.error(f"  - Could not save debugging info: {e}")
            
            return False
        
        logger.info(f"  - Login form detected: {form_result.get('selector')}")
        
        # Find and input username field
        logger.info("  - Searching for username field...")
        username_selectors = [
            (By.NAME, "username"),
            (By.NAME, "email"),
            (By.CSS_SELECTOR, "input[type='text']"),
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.CSS_SELECTOR, "input[placeholder*='username' i]"),
            (By.CSS_SELECTOR, "input[placeholder*='email' i]")
        ]
        
        username_element = None
        for i, (selector_type, selector_value) in enumerate(username_selectors, 1):
            logger.info(f"    - Attempt {i}/{len(username_selectors)}: {selector_type.name}='{selector_value}'")
            try:
                username_element = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((selector_type, selector_value))
                )
                logger.info(f"    - SUCCESS: Username field found with {selector_type.name}='{selector_value}'")
                break
            except TimeoutException:
                logger.info(f"    - Failed: Timeout for {selector_type.name}='{selector_value}'")
                continue
        
        if not username_element:
            logger.error("  - Username field not found with any selector")
            return False
        
        # Find password field
        logger.info("  - Searching for password field...")
        try:
            password_element = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password']"))
            )
            logger.info("  - Password field found successfully")
        except TimeoutException:
            logger.error("  - Password field not found")
            return False
        
        # Input login credentials
        logger.info("  - Entering login credentials...")
        try:
            username_element.clear()
            username_element.send_keys(username)
            logger.info(f"  - Username entered: {username}")
            
            password_element.clear()
            password_element.send_keys(password)
            logger.info("  - Password entered: [HIDDEN]")
        except Exception as e:
            logger.error(f"  - Failed to enter credentials: {e}")
            return False
        
        # Attempt login
        logger.info("  - Attempting to submit login form...")
        try:
            submit_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
            )
            submit_button.click()
            logger.info("  - Login button clicked successfully")
        except TimeoutException:
            logger.info("  - Submit button not found, trying Enter key...")
            try:
                password_element.send_keys("\n")
                logger.info("  - Enter key pressed for login")
            except Exception as e:
                logger.error(f"  - Failed to submit with Enter key: {e}")
                return False
        
        # Wait for login completion
        logger.info("  - Waiting for login to complete...")
        time.sleep(5)
        
        # Verify login success
        current_url = driver.current_url
        if "/auth/login" not in current_url:
            logger.info(f"  - Login successful! Current URL: {current_url}")
            return True
        else:
            logger.error("  - Login failed - Still on login page")
            logger.error(f"    Current URL: {current_url}")
            
            # Check for error messages
            try:
                error_elements = driver.find_elements(By.CSS_SELECTOR, ".error, .alert, .warning, [class*='error'], [class*='alert']")
                if error_elements:
                    for i, elem in enumerate(error_elements):
                        if elem.is_displayed():
                            logger.error(f"    Error message {i+1}: {elem.text}")
            except:
                logger.warning("    Could not check for error messages")
            
            driver.save_screenshot("login_failed.png")
            logger.info("  - Screenshot saved: login_failed.png")
            return False
    
    def wait_for_question_load(self, driver, wait_seconds=10):
        """Wait for Question page chart loading completion"""
        logger.info("Step 3/3: Loading question chart...")
        
        # Wait for chart related elements to appear
        logger.info("  - Searching for chart elements...")
        chart_selectors = [
            ".Visualization",
            "[data-testid='query-visualization-root']", 
            ".QueryBuilder-section",
            ".Card .Card-content",
            "svg", # Many charts are rendered as SVG
            "canvas" # Some charts use Canvas
        ]
        
        chart_found = False
        for i, selector in enumerate(chart_selectors, 1):
            logger.info(f"    - Attempt {i}/{len(chart_selectors)}: Looking for '{selector}'")
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                logger.info(f"    - SUCCESS: Chart element found with '{selector}'")
                chart_found = True
                break
            except TimeoutException:
                logger.info(f"    - Failed: Timeout for '{selector}'")
                continue
        
        if not chart_found:
            logger.warning("  - No chart elements found, but continuing process")
        
        # Wait for loading spinners to disappear
        logger.info("  - Checking for loading spinners...")
        try:
            WebDriverWait(driver, 10).until_not(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".Loading, .LoadingSpinner, [data-testid='loading-spinner']"))
            )
            logger.info("  - Loading spinners disappeared")
        except TimeoutException:
            logger.info("  - Loading spinner check timeout, continuing...")
        
        # Additional safety wait
        logger.info(f"  - Additional safety wait: {wait_seconds} seconds")
        time.sleep(wait_seconds)
        
        # Verify rendering completion with JavaScript
        logger.info("  - Verifying chart rendering with JavaScript...")
        try:
            is_ready = driver.execute_script("""
                // Check if chart is actually rendered
                const charts = document.querySelectorAll('svg, canvas, .Visualization');
                return {
                    count: charts.length,
                    ready: charts.length > 0
                };
            """)
            
            if is_ready.get('ready'):
                logger.info(f"  - Chart rendering verified: {is_ready.get('count')} chart elements found")
            else:
                logger.warning("  - No chart elements found in JavaScript verification")
        except Exception as e:
            logger.error(f"  - JavaScript verification error: {e}")
    
    def capture_question_chart(self, driver):
        """Capture only chart area from Question page"""
        logger.info("  - Starting chart area capture...")
        
        try:
            # Try various chart selectors
            chart_selectors = [
                ".Visualization",
                "[data-testid='query-visualization-root']",
                ".QueryBuilder-section .Card",
                ".Card .Card-content",
                ".Question .Card"
            ]
            
            chart_element = None
            for i, selector in enumerate(chart_selectors, 1):
                logger.info(f"    - Chart capture attempt {i}/{len(chart_selectors)}: '{selector}'")
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    logger.info(f"      - Found {len(elements)} elements with this selector")
                    
                    for j, element in enumerate(elements):
                        size = element.size
                        is_displayed = element.is_displayed()
                        logger.info(f"      - Element {j+1}: size={size}, displayed={is_displayed}")
                        
                        if is_displayed and size['width'] > 100 and size['height'] > 100:
                            chart_element = element
                            logger.info(f"    - SUCCESS: Chart element selected with '{selector}'")
                            logger.info(f"      - Final element size: {size}")
                            break
                    if chart_element:
                        break
                except Exception as e:
                    logger.info(f"      - Error with selector '{selector}': {e}")
                    continue
            
            if chart_element:
                logger.info("  - Capturing chart element screenshot...")
                screenshot_data = chart_element.screenshot_as_png
                logger.info("  - Chart area screenshot captured successfully")
                return screenshot_data
            else:
                logger.warning("  - Chart element not found, capturing full page instead")
                screenshot_data = driver.get_screenshot_as_png()
                logger.info("  - Full page screenshot captured")
                return screenshot_data
                
        except Exception as e:
            logger.error(f"  - Chart capture failed: {e}")
            logger.info("  - Falling back to full page capture...")
            screenshot_data = driver.get_screenshot_as_png()
            logger.info("  - Full page screenshot captured as fallback")
            return screenshot_data
    
    def capture_question(self, question_id=None, username=None, password=None, wait_seconds=10, crop_to_chart=True):
        """Capture Question URL as PNG"""
        logger.info("="*60)
        logger.info("STARTING METABASE SCREENSHOT CAPTURE")
        logger.info("="*60)
        
        # Use default values if not provided
        question_id = question_id or DEFAULT_QUESTION_ID
        username = username or DEFAULT_USERNAME
        password = password or DEFAULT_PASSWORD
        
        logger.info(f"Configuration:")
        logger.info(f"  - Base URL: {METABASE_BASE_URL}")
        logger.info(f"  - Question ID: {question_id}")
        logger.info(f"  - Username: {username}")
        logger.info(f"  - Wait seconds: {wait_seconds}")
        logger.info(f"  - Crop to chart: {crop_to_chart}")
        logger.info(f"  - Debug port range: {DEBUG_PORT_RANGE[0]}-{DEBUG_PORT_RANGE[1]}")
        
        logger.info("Initializing Firefox WebDriver...")
        try:
            driver = self.create_firefox_driver()
        except Exception as e:
            logger.error(f"Failed to initialize Firefox WebDriver: {e}")
            raise
        
        try:
            # Login
            logger.info("\n" + "="*40)
            logger.info("PHASE 1: AUTHENTICATION")
            logger.info("="*40)
            
            if not self.login_to_metabase(driver, username, password):
                raise Exception("Authentication failed")
            
            logger.info("Authentication completed successfully!")
            
            # Navigate to Question page
            logger.info("\n" + "="*40)
            logger.info("PHASE 2: NAVIGATION")
            logger.info("="*40)
            
            question_url = f"{METABASE_BASE_URL}/question/{question_id}"
            logger.info(f"Navigating to Question page: {question_url}")
            
            try:
                driver.get(question_url)
                logger.info("Question page loaded successfully")
                logger.info(f"Current URL: {driver.current_url}")
            except Exception as e:
                logger.error(f"Failed to load question page: {e}")
                raise
            
            # Wait for chart loading completion
            logger.info("\n" + "="*40)
            logger.info("PHASE 3: CHART LOADING")
            logger.info("="*40)
            
            self.wait_for_question_load(driver, wait_seconds)
            logger.info("Chart loading phase completed")
            
            # Capture screenshot
            logger.info("\n" + "="*40)
            logger.info("PHASE 4: SCREENSHOT CAPTURE")
            logger.info("="*40)
            
            if crop_to_chart:
                logger.info("Capturing chart area only...")
                screenshot_png = self.capture_question_chart(driver)
            else:
                logger.info("Capturing full page...")
                screenshot_png = driver.get_screenshot_as_png()
            
            screenshot_size = len(screenshot_png)
            logger.info(f"Screenshot captured successfully")
            logger.info(f"Screenshot size: {screenshot_size:,} bytes ({screenshot_size/1024:.1f} KB)")
            
            logger.info("\n" + "="*60)
            logger.info("SCREENSHOT CAPTURE COMPLETED SUCCESSFULLY!")
            logger.info("="*60)
            
            return screenshot_png
                
        except Exception as e:
            logger.error(f"\n" + "="*60)
            logger.error("SCREENSHOT CAPTURE FAILED!")
            logger.error("="*60)
            logger.error(f"Error: {e}")
            
            try:
                driver.save_screenshot("capture_error.png")
                logger.info("Error screenshot saved: capture_error.png")
            except:
                logger.error("Failed to save error screenshot")
            
            raise
        finally:
            logger.info("Closing Firefox WebDriver...")
            try:
                driver.quit()
                logger.info("Firefox WebDriver closed successfully")
            except:
                logger.error("Failed to close Firefox WebDriver")

# Service instance
screenshot_service = MetabaseScreenshotService()

@app.route('/screenshot', methods=['POST'])
def take_screenshot():
    """API to convert Question to PNG"""
    request_id = int(time.time())
    logger.info(f"\n" + "+"*60)
    logger.info(f"NEW API REQUEST - ID: {request_id}")
    logger.info("+"*60)
    
    try:
        data = request.json or {}
        question_id = data.get('question_id')
        username = data.get('username')
        password = data.get('password')
        wait_seconds = data.get('wait_seconds', 10)
        crop_to_chart = data.get('crop_to_chart', True)
        return_base64 = data.get('return_base64', True)
        
        logger.info(f"Request parameters:")
        logger.info(f"  - Question ID: {question_id or DEFAULT_QUESTION_ID}")
        logger.info(f"  - Username: {username or DEFAULT_USERNAME}")
        logger.info(f"  - Wait seconds: {wait_seconds}")
        logger.info(f"  - Crop to chart: {crop_to_chart}")
        logger.info(f"  - Return Base64: {return_base64}")
        
        # Capture screenshot
        start_time = time.time()
        screenshot_png = screenshot_service.capture_question(
            question_id=question_id,
            username=username,
            password=password,
            wait_seconds=wait_seconds,
            crop_to_chart=crop_to_chart
        )
        end_time = time.time()
        
        total_time = end_time - start_time
        logger.info(f"Total processing time: {total_time:.2f} seconds")
        
        if return_base64:
            logger.info("Converting to Base64...")
            image_base64 = base64.b64encode(screenshot_png).decode()
            logger.info(f"Base64 conversion completed: {len(image_base64):,} characters")
            
            response = {
                "success": True,
                "image_base64": image_base64,
                "timestamp": datetime.now().isoformat(),
                "question_id": question_id or DEFAULT_QUESTION_ID,
                "base_url": METABASE_BASE_URL,
                "processing_time": round(total_time, 2),
                "image_size": len(screenshot_png)
            }
            
            logger.info(f"API Request {request_id} completed successfully")
            return jsonify(response)
        else:
            logger.info("Returning binary file...")
            filename = f'metabase_question_{question_id or DEFAULT_QUESTION_ID}_{int(time.time())}.png'
            logger.info(f"Filename: {filename}")
            
            return send_file(
                io.BytesIO(screenshot_png),
                mimetype='image/png',
                as_attachment=True,
                download_name=filename
            )
            
    except Exception as e:
        logger.error(f"API Request {request_id} failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "request_id": request_id,
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Service health check"""
    logger.info("Health check requested")
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "Metabase Screenshot Service",
        "base_url": METABASE_BASE_URL,
        "default_question_id": DEFAULT_QUESTION_ID,
        "debug_port_range": f"{DEBUG_PORT_RANGE[0]}-{DEBUG_PORT_RANGE[1]}"
    })

@app.route('/test', methods=['POST'])
def test_login():
    """Login test endpoint"""
    logger.info("Login test requested")
    
    try:
        data = request.json or {}
        username = data.get('username') or DEFAULT_USERNAME
        password = data.get('password') or DEFAULT_PASSWORD
        
        logger.info(f"Testing login with username: {username}")
        
        driver = screenshot_service.create_firefox_driver()
        
        try:
            result = screenshot_service.login_to_metabase(driver, username, password)
            
            response = {
                "success": result,
                "message": "Login successful" if result else "Login failed",
                "current_url": driver.current_url,
                "base_url": METABASE_BASE_URL,
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"Login test result: {'SUCCESS' if result else 'FAILED'}")
            return jsonify(response)
            
        finally:
            driver.quit()
            
    except Exception as e:
        logger.error(f"Login test error: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    logger.info("Configuration requested")
    return jsonify({
        "base_url": METABASE_BASE_URL,
        "default_question_id": DEFAULT_QUESTION_ID,
        "default_username": DEFAULT_USERNAME,
        "debug_port_range": f"{DEBUG_PORT_RANGE[0]}-{DEBUG_PORT_RANGE[1]}"
    })

@app.route('/ports', methods=['GET'])
def check_ports():
    """Check available ports in range"""
    available_ports = []
    used_ports = []
    
    for port in range(DEBUG_PORT_RANGE[0], DEBUG_PORT_RANGE[1] + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                available_ports.append(port)
        except OSError:
            used_ports.append(port)
    
    return jsonify({
        "port_range": f"{DEBUG_PORT_RANGE[0]}-{DEBUG_PORT_RANGE[1]}",
        "available_ports": available_ports,
        "used_ports": used_ports,
        "available_count": len(available_ports),
        "used_count": len(used_ports)
    })

if __name__ == '__main__':
    logger.info("="*60)
    logger.info("METABASE SCREENSHOT SERVICE STARTING")
    logger.info("="*60)
    logger.info("Available endpoints:")
    logger.info("   POST /screenshot - Convert Question to PNG")
    logger.info("   POST /test - Login test")
    logger.info("   GET /health - Service health check")
    logger.info("   GET /config - View current configuration")
    logger.info("   GET /ports - Check available debug ports")
    logger.info(f"Configuration:")
    logger.info(f"   Base URL: {METABASE_BASE_URL}")
    logger.info(f"   Default Question ID: {DEFAULT_QUESTION_ID}")
    logger.info(f"   Default Username: {DEFAULT_USERNAME}")
    logger.info(f"   Debug Port Range: {DEBUG_PORT_RANGE[0]}-{DEBUG_PORT_RANGE[1]}")
    logger.info("="*60)
    logger.info("Server starting on: http://0.0.0.0:5000")
    logger.info("="*60)
    
    app.run(host='0.0.0.0',
복사
Notion에 저장
피드백
끝?
네, 끝났습니다! 마지막 부분이 잘렸네요.

Copy    app.run(host='0.0.0.0', port=5000, debug=False)
주요 변경사항
✅ 포트 관리: 8030-8049 범위에서 사용 가능한 포트 자동 찾기
✅ 디버그 포트: --remote-debugging-port 설정으로 포트 충돌 방지
✅ 포트 체크 API: /ports 엔드포인트로 사용 가능한 포트 확인
✅ 강화된 에러 처리: 페이지 로드 실패 시 더 자세한 디버깅 정보
✅ 연결 문제 감지: 페이지 소스와 URL을 체크해서 연결 문제 조기 발견

새로운 엔드포인트
Copy# 사용 가능한 포트 확인
curl http://localhost:5000/ports
이제 Firefox가 8030-8049 포트 중 사용 가능한 것을 자동으로 선택해서 사용하므로 포트 충돌 문제가 해결될 것입니다! 🎯
