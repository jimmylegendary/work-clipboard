# metabase_screenshot_service.py
from flask import Flask, request, jsonify, send_file
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import base64
import time
import io
from datetime import datetime

app = Flask(__name__)

class MetabaseScreenshotService:
    def __init__(self):
        self.chrome_options = Options()
        self.chrome_options.add_argument("--headless")
        self.chrome_options.add_argument("--no-sandbox")
        self.chrome_options.add_argument("--disable-dev-shm-usage")
        self.chrome_options.add_argument("--disable-gpu")
        self.chrome_options.add_argument("--window-size=1400,1000")
        self.chrome_options.add_argument("--disable-extensions")
        # 실제 브라우저처럼 User-Agent 설정
        self.chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
    def wait_for_dynamic_elements(self, driver, max_wait=30):
        """JavaScript 동적 렌더링 완료까지 대기"""
        print("⏳ 동적 컨텐츠 로딩 대기 중...")
        
        # 1. 페이지 로드 완료 대기
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        
        # 2. JavaScript 실행 추가 대기
        time.sleep(5)
        
        # 3. JavaScript로 로그인 폼 존재 확인
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
            print(f"JavaScript 대기 오류: {e}")
            return {"found": False, "error": str(e)}
    
    def login_to_metabase(self, driver, base_url, username, password):
        """동적 렌더링을 고려한 Metabase 로그인"""
        login_url = f"{base_url}/auth/login"
        print(f"🔗 로그인 페이지 접속: {login_url}")
        
        driver.get(login_url)
        print(f"📍 현재 URL: {driver.current_url}")
        
        # 동적 요소 로딩 대기
        form_result = self.wait_for_dynamic_elements(driver)
        
        if not form_result.get("found"):
            print("❌ 로그인 폼을 찾을 수 없음")
            driver.save_screenshot("login_form_not_found.png")
            return False
        
        print(f"✅ 로그인 폼 발견: {form_result.get('selector')}")
        
        # Username 필드 찾기 및 입력
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
                print(f"✅ Username 필드 발견: {selector_type.name}='{selector_value}'")
                break
            except TimeoutException:
                continue
        
        if not username_element:
            print("❌ Username 필드를 찾을 수 없음")
            return False
        
        # Password 필드 찾기
        try:
            password_element = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password']"))
            )
            print("✅ Password 필드 발견")
        except TimeoutException:
            print("❌ Password 필드를 찾을 수 없음")
            return False
        
        # 로그인 정보 입력
        print("🔑 로그인 정보 입력 중...")
        username_element.clear()
        username_element.send_keys(username)
        
        password_element.clear()
        password_element.send_keys(password)
        
        # 로그인 시도
        try:
            submit_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
            )
            submit_button.click()
            print("✅ 로그인 버튼 클릭")
        except TimeoutException:
            # Enter 키로 대체 시도
            password_element.send_keys("\n")
            print("✅ Enter 키로 로그인 시도")
        
        # 로그인 완료 대기
        time.sleep(5)
        
        # 로그인 성공 확인
        if "/auth/login" not in driver.current_url:
            print(f"✅ 로그인 성공 - 현재 URL: {driver.current_url}")
            return True
        else:
            print("❌ 로그인 실패 - 여전히 로그인 페이지에 있음")
            driver.save_screenshot("login_failed.png")
            return False
    
    def wait_for_question_load(self, driver, wait_seconds=10):
        """Question 페이지의 차트 로딩 완료 대기"""
        print("⏳ Question 차트 로딩 대기 중...")
        
        # 차트 관련 요소들이 나타날 때까지 대기
        chart_selectors = [
            ".Visualization",
            "[data-testid='query-visualization-root']", 
            ".QueryBuilder-section",
            ".Card .Card-content",
            "svg", # 많은 차트가 SVG로 렌더링됨
            "canvas" # 일부 차트는 Canvas 사용
        ]
        
        chart_found = False
        for selector in chart_selectors:
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                print(f"✅ 차트 요소 발견: {selector}")
                chart_found = True
                break
            except TimeoutException:
                continue
        
        if not chart_found:
            print("⚠️ 차트 요소를 찾지 못했지만 계속 진행")
        
        # 로딩 스피너가 사라질 때까지 대기
        try:
            WebDriverWait(driver, 10).until_not(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".Loading, .LoadingSpinner, [data-testid='loading-spinner']"))
            )
            print("✅ 로딩 완료")
        except TimeoutException:
            print("⚠️ 로딩 스피너 확인 실패, 추가 대기")
        
        # 추가 안전 대기
        time.sleep(wait_seconds)
        
        # JavaScript 실행으로 렌더링 완료 확인
        try:
            is_ready = driver.execute_script("""
                // 차트가 실제로 렌더링되었는지 확인
                const charts = document.querySelectorAll('svg, canvas, .Visualization');
                return charts.length > 0;
            """)
            
            if is_ready:
                print("✅ 차트 렌더링 확인 완료")
            else:
                print("⚠️ 차트 렌더링 확인 실패")
        except Exception as e:
            print(f"⚠️ JavaScript 렌더링 확인 오류: {e}")
    
    def capture_question_chart(self, driver):
        """Question 페이지에서 차트 영역만 캡처"""
        try:
            # 다양한 차트 선택자 시도
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
                            print(f"✅ 차트 요소 선택: {selector}")
                            break
                    if chart_element:
                        break
                except Exception as e:
                    continue
            
            if chart_element:
                return chart_element.screenshot_as_png
            else:
                print("⚠️ 차트 요소를 찾지 못해 전체 페이지 캡처")
                return driver.get_screenshot_as_png()
                
        except Exception as e:
            print(f"⚠️ 차트 캡처 실패, 전체 페이지 캡처: {e}")
            return driver.get_screenshot_as_png()
    
    def capture_question(self, question_url, username, password, wait_seconds=10, crop_to_chart=True):
        """Question URL을 PNG로 캡처"""
        driver = webdriver.Chrome(options=self.chrome_options)
        
        try:
            # Metabase 기본 URL 추출
            base_url = question_url.split('/question')[0]
            print(f"🏠 Metabase 기본 URL: {base_url}")
            
            # 로그인
            if not self.login_to_metabase(driver, base_url, username, password):
                raise Exception("로그인 실패")
            
            # Question 페이지로 이동
            print(f"📊 Question 페이지 이동: {question_url}")
            driver.get(question_url)
            
            # 차트 로딩 완료 대기
            self.wait_for_question_load(driver, wait_seconds)
            
            # 스크린샷 캡처
            if crop_to_chart:
                screenshot_png = self.capture_question_chart(driver)
            else:
                screenshot_png = driver.get_screenshot_as_png()
            
            print("✅ 스크린샷 캡처 완료")
            return screenshot_png
                
        except Exception as e:
            print(f"❌ 캡처 실패: {e}")
            driver.save_screenshot("capture_error.png")
            raise
        finally:
            driver.quit()

# 서비스 인스턴스 생성
screenshot_service = MetabaseScreenshotService()

@app.route('/screenshot', methods=['POST'])
def take_screenshot():
    """Question URL을 PNG로 변환하는 API"""
    try:
        data = request.json
        question_url = data.get('question_url')
        username = data.get('username')
        password = data.get('password')
        wait_seconds = data.get('wait_seconds', 10)
        crop_to_chart = data.get('crop_to_chart', True)
        return_base64 = data.get('return_base64', True)
        
        if not all([question_url, username, password]):
            return jsonify({
                "success": False,
                "error": "question_url, username, password are required"
            }), 400
        
        print(f"📋 스크린샷 요청:")
        print(f"   - URL: {question_url}")
        print(f"   - Username: {username}")
        print(f"   - Wait: {wait_seconds}s")
        print(f"   - Crop: {crop_to_chart}")
        
        # 스크린샷 캡처
        screenshot_png = screenshot_service.capture_question(
            question_url=question_url,
            username=username,
            password=password,
            wait_seconds=wait_seconds,
            crop_to_chart=crop_to_chart
        )
        
        if return_base64:
            # Base64로 반환
            image_base64 = base64.b64encode(screenshot_png).decode()
            return jsonify({
                "success": True,
                "image_base64": image_base64,
                "timestamp": datetime.now().isoformat(),
                "question_url": question_url
            })
        else:
            # 바이너리 파일로 반환
            return send_file(
                io.BytesIO(screenshot_png),
                mimetype='image/png',
                as_attachment=True,
                download_name=f'metabase_question_{int(time.time())}.png'
            )
            
    except Exception as e:
        print(f"❌ API 오류: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """서비스 상태 확인"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "Metabase Screenshot Service"
    })

@app.route('/test', methods=['POST'])
def test_login():
    """로그인 테스트용 엔드포인트"""
    try:
        data = request.json
        base_url = data.get('base_url')
        username = data.get('username')
        password = data.get('password')
        
        driver = webdriver.Chrome(options=screenshot_service.chrome_options)
        
        try:
            result = screenshot_service.login_to_metabase(driver, base_url, username, password)
            
            return jsonify({
                "success": result,
                "message": "로그인 성공" if result else "로그인 실패",
                "current_url": driver.current_url
            })
            
        finally:
            driver.quit()
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

if __name__ == '__main__':
    print("🚀 Metabase Screenshot Service 시작")
    print("📋 사용 가능한 엔드포인트:")
    print("   POST /screenshot - Question URL을 PNG로 변환")
    print("   POST /test - 로그인 테스트")
    print("   GET /health - 서비스 상태 확인")
    print("🌐 서버 시작: http://0.0.0.0:5000")
    
    app.run(host='0.0.0.0', port=5000, debug=False)
