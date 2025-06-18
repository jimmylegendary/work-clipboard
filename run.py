# metabase_screenshot_service.py
from flask import Flask, request, jsonify, send_file
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import base64
import time
import io
from datetime import datetime

# Configuration
METABASE_BASE_URL = "http://your-metabase.com"
DEFAULT_QUESTION_ID = "123"
DEFAULT_USERNAME = "your-username"
DEFAULT_PASSWORD = "your-password"

app = Flask(__name__)

class MetabaseScreenshotService:
    def __init__(self):
        self.firefox_options = Options()
        self.firefox_options.add_argument("--headless")
        self.firefox_options.add_argument("--no-sandbox")
        self.firefox_options.add_argument("--disable-dev-shm-usage")
        self.firefox_options.add_argument("--width=1400")
        self.firefox_options.add_argument("--height=1000")
        # Set real browser User-Agent
        self.firefox_options.set_preference("general.useragent.override", 
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0")
        
    def wait_for_dynamic_elements(self, driver, max_wait=30):
        """Wait for JavaScript dynamic rendering completion"""
        print("Waiting for dynamic content loading...")
        
        # 1. Wait for page load completion
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        
        # 2. Additional wait for JavaScript execution
        time.sleep(5)
        
        # 3. Check login form existence with JavaScript
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
                            selector: selector
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
            result = driver.execute_async_script(wait_script)
            return result
        except Exception as e:
            print(f"JavaScript wait error: {e}")
            return {"found": False, "error": str(e)}
    
    def login_to_metabase(self, driver, username, password):
        """Login to Metabase with dynamic rendering consideration"""
        login_url = f"{METABASE_BASE_URL}/auth/login"
        print(f"Accessing login page: {login_url}")
        
        driver.get(login_url)
        print(f"Current URL: {driver.current_url}")
        
        # Wait for dynamic elements loading
        form_result = self.wait_for_dynamic_elements(driver)
        
        if not form_result.get("found"):
            print("Login form not found")
            driver.save_screenshot("login_form_not_found.png")
            return False
        
        print(f"Login form found: {form_result.get('selector')}")
        
        # Find and input username field
        username_selectors = [
            (By.NAME, "username"),
            (By.NAME, "email"),
            (By.CSS_SELECTOR, "input[type='text']"),
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.CSS_SELECTOR, "input[placeholder*='username' i]"),
            (By.CSS_SELECTOR, "input[placeholder*='email' i]")
        ]
        
        username_element = None
        for selector_type, selector_value in username_selectors:
            try:
                username_element = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((selector_type, selector_value))
                )
                print(f"Username field found: {selector_type.name}='{selector_value}'")
                break
            except TimeoutException:
                continue
        
        if not username_element:
            print("Username field not found")
            return False
        
        # Find password field
        try:
            password_element = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password']"))
            )
            print("Password field found")
        except TimeoutException:
            print("Password field not found")
            return False
        
        # Input login credentials
        print("Entering login credentials...")
        username_element.clear()
        username_element.send_keys(username)
        
        password_element.clear()
        password_element.send_keys(password)
        
        # Attempt login
        try:
            submit_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
            )
            submit_button.click()
            print("Login button clicked")
        except TimeoutException:
            # Try Enter key as alternative
            password_element.send_keys("\n")
            print("Login attempted with Enter key")
        
        # Wait for login completion
        time.sleep(5)
        
        # Verify login success
        if "/auth/login" not in driver.current_url:
            print(f"Login successful - Current URL: {driver.current_url}")
            return True
        else:
            print("Login failed - Still on login page")
            driver.save_screenshot("login_failed.png")
            return False
    
    def wait_for_question_load(self, driver, wait_seconds=10):
        """Wait for Question page chart loading completion"""
        print("Waiting for question chart loading...")
        
        # Wait for chart related elements to appear
        chart_selectors = [
            ".Visualization",
            "[data-testid='query-visualization-root']", 
            ".QueryBuilder-section",
            ".Card .Card-content",
            "svg", # Many charts are rendered as SVG
            "canvas" # Some charts use Canvas
        ]
        
        chart_found = False
        for selector in chart_selectors:
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                print(f"Chart element found: {selector}")
                chart_found = True
                break
            except TimeoutException:
                continue
        
        if not chart_found:
            print("Chart element not found but continuing")
        
        # Wait for loading spinners to disappear
        try:
            WebDriverWait(driver, 10).until_not(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".Loading, .LoadingSpinner, [data-testid='loading-spinner']"))
            )
            print("Loading completed")
        except TimeoutException:
            print("Loading spinner check failed, additional wait")
        
        # Additional safety wait
        time.sleep(wait_seconds)
        
        # Verify rendering completion with JavaScript
        try:
            is_ready = driver.execute_script("""
                // Check if chart is actually rendered
                const charts = document.querySelectorAll('svg, canvas, .Visualization');
                return charts.length > 0;
            """)
            
            if is_ready:
                print("Chart rendering verification completed")
            else:
                print("Chart rendering verification failed")
        except Exception as e:
            print(f"JavaScript rendering check error: {e}")
    
    def capture_question_chart(self, driver):
        """Capture only chart area from Question page"""
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
            for selector in chart_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_displayed() and element.size['width'] > 100 and element.size['height'] > 100:
                            chart_element = element
                            print(f"Chart element selected: {selector}")
                            break
                    if chart_element:
                        break
                except Exception as e:
                    continue
            
            if chart_element:
                return chart_element.screenshot_as_png
            else:
                print("Chart element not found, capturing full page")
                return driver.get_screenshot_as_png()
                
        except Exception as e:
            print(f"Chart capture failed, capturing full page: {e}")
            return driver.get_screenshot_as_png()
    
    def capture_question(self, question_id=None, username=None, password=None, wait_seconds=10, crop_to_chart=True):
        """Capture Question URL as PNG"""
        driver = webdriver.Firefox(options=self.firefox_options)
        
        try:
            # Use default values if not provided
            question_id = question_id or DEFAULT_QUESTION_ID
            username = username or DEFAULT_USERNAME
            password = password or DEFAULT_PASSWORD
            
            print(f"Metabase base URL: {METABASE_BASE_URL}")
            print(f"Question ID: {question_id}")
            
            # Login
            if not self.login_to_metabase(driver, username, password):
                raise Exception("Login failed")
            
            # Navigate to Question page
            question_url = f"{METABASE_BASE_URL}/question/{question_id}"
            print(f"Navigating to Question page: {question_url}")
            driver.get(question_url)
            
            # Wait for chart loading completion
            self.wait_for_question_load(driver, wait_seconds)
            
            # Capture screenshot
            if crop_to_chart:
                screenshot_png = self.capture_question_chart(driver)
            else:
                screenshot_png = driver.get_screenshot_as_png()
            
            print("Screenshot capture completed")
            return screenshot_png
                
        except Exception as e:
            print(f"Capture failed: {e}")
            driver.save_screenshot("capture_error.png")
            raise
        finally:
            driver.quit()

# Service instance
screenshot_service = MetabaseScreenshotService()

@app.route('/screenshot', methods=['POST'])
def take_screenshot():
    """API to convert Question to PNG"""
    try:
        data = request.json or {}
        question_id = data.get('question_id')
        username = data.get('username')
        password = data.get('password')
        wait_seconds = data.get('wait_seconds', 10)
        crop_to_chart = data.get('crop_to_chart', True)
        return_base64 = data.get('return_base64', True)
        
        print(f"Screenshot request:")
        print(f"   - Question ID: {question_id or DEFAULT_QUESTION_ID}")
        print(f"   - Username: {username or DEFAULT_USERNAME}")
        print(f"   - Wait: {wait_seconds}s")
        print(f"   - Crop: {crop_to_chart}")
        
        # Capture screenshot
        screenshot_png = screenshot_service.capture_question(
            question_id=question_id,
            username=username,
            password=password,
            wait_seconds=wait_seconds,
            crop_to_chart=crop_to_chart
        )
        
        if return_base64:
            # Return as Base64
            image_base64 = base64.b64encode(screenshot_png).decode()
            return jsonify({
                "success": True,
                "image_base64": image_base64,
                "timestamp": datetime.now().isoformat(),
                "question_id": question_id or DEFAULT_QUESTION_ID,
                "base_url": METABASE_BASE_URL
            })
        else:
            # Return as binary file
            return send_file(
                io.BytesIO(screenshot_png),
                mimetype='image/png',
                as_attachment=True,
                download_name=f'metabase_question_{question_id or DEFAULT_QUESTION_ID}_{int(time.time())}.png'
            )
            
    except Exception as e:
        print(f"API error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Service health check"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "Metabase Screenshot Service",
        "base_url": METABASE_BASE_URL,
        "default_question_id": DEFAULT_QUESTION_ID
    })

@app.route('/test', methods=['POST'])
def test_login():
    """Login test endpoint"""
    try:
        data = request.json or {}
        username = data.get('username') or DEFAULT_USERNAME
        password = data.get('password') or DEFAULT_PASSWORD
        
        driver = webdriver.Firefox(options=screenshot_service.firefox_options)
        
        try:
            result = screenshot_service.login_to_metabase(driver, username, password)
            
            return jsonify({
                "success": result,
                "message": "Login successful" if result else "Login failed",
                "current_url": driver.current_url,
                "base_url": METABASE_BASE_URL
            })
            
        finally:
            driver.quit()
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    return jsonify({
        "base_url": METABASE_BASE_URL,
        "default_question_id": DEFAULT_QUESTION_ID,
        "default_username": DEFAULT_USERNAME
    })

if __name__ == '__main__':
    print("Metabase Screenshot Service Starting")
    print("Available endpoints:")
    print("   POST /screenshot - Convert Question to PNG")
    print("   POST /test - Login test")
    print("   GET /health - Service health check")
    print("   GET /config - View current configuration")
    print(f"Configuration:")
    print(f"   Base URL: {METABASE_BASE_URL}")
    print(f"   Default Question ID: {DEFAULT_QUESTION_ID}")
    print(f"   Default Username: {DEFAULT_USERNAME}")
    print("Server starting: http://0.0.0.0:5000")
    
    app.run(host='0.0.0.0', port=5000, debug=False)
