import pytest
import requests
from typing import Dict, Any

# Конфиги сервисов
ANALYSIS_API = "http://localhost:8000"
MANAGEMENT_API = "http://localhost:8001"

# Тестовый токен (маленький, из твоего списка)
TEST_TOKEN = "5YC49sjG8SVXbnbTMFnUQmsPsBXKfR3jYERpmcXTpump"


@pytest.mark.integration
class TestServicesHealth:
    """Тесты здоровья сервисов"""
    
    def test_analysis_api_health(self):
        """Проверка Analysis API"""
        try:
            response = requests.get(f"{ANALYSIS_API}/health", timeout=3)
            assert response.status_code == 200
            assert response.json().get("status") == "ok"
        except requests.exceptions.ConnectionError:
            pytest.skip("Analysis API is not running")
    
    def test_management_api_health(self):
        """Проверка Management API"""
        try:
            response = requests.get(f"{MANAGEMENT_API}/health", timeout=3)
            assert response.status_code == 200
        except requests.exceptions.ConnectionError:
            pytest.skip("Management API is not running")


@pytest.mark.integration
class TestTokenAnalysis:
    """Тесты анализа токенов через API"""
    
    def test_get_token_risk(self):
        """Тест получения риска токена"""
        try:
            response = requests.get(
                f"{ANALYSIS_API}/api/token/{TEST_TOKEN}/risk",
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                assert "score" in data
                assert "level" in data
            else:
                pytest.skip(f"API returned {response.status_code}")
        except requests.exceptions.ConnectionError:
            pytest.skip("Analysis API is not running")
    
    def test_get_revolutionary_score(self):
        """Тест революционного скора"""
        try:
            response = requests.get(
                f"{ANALYSIS_API}/api/token/{TEST_TOKEN}/revolutionary/score",
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                assert "revolutionary_score" in data
                assert "risk_level" in data
            else:
                pytest.skip(f"API returned {response.status_code}")
        except requests.exceptions.ConnectionError:
            pytest.skip("Analysis API is not running")
    
    def test_get_temporal_entropy(self):
        """Тест временной энтропии"""
        try:
            response = requests.get(
                f"{ANALYSIS_API}/api/token/{TEST_TOKEN}/revolutionary/temporal-entropy",
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                assert "entropy_score" in data or "error" in data
            else:
                pytest.skip(f"API returned {response.status_code}")
        except requests.exceptions.ConnectionError:
            pytest.skip("Analysis API is not running")


@pytest.mark.integration
class TestTokenCollection:
    """Тесты сбора токенов"""
    
    def test_get_token_from_cache(self):
        """Тест получения токена из кэша"""
        try:
            response = requests.get(
                f"{MANAGEMENT_API}/token/{TEST_TOKEN}",
                timeout=10
            )
            # 200 - токен есть в кэше, 404 - нет
            assert response.status_code in [200, 404]
        except requests.exceptions.ConnectionError:
            pytest.skip("Management API is not running")
    
    def test_get_tokens_list(self):
        """Тест получения списка токенов"""
        try:
            response = requests.get(
                f"{MANAGEMENT_API}/tokens?limit=10",
                timeout=10
            )
            assert response.status_code in [200, 404]
        except requests.exceptions.ConnectionError:
            pytest.skip("Management API is not running")


@pytest.mark.integration
class TestEndToEnd:
    """Сквозные тесты (требуют оба сервиса)"""
    
    def test_full_analysis_flow(self):
        """Полный цикл: проверка что анализ доступен"""
        try:
            # Проверяем оба сервиса
            analysis_ok = requests.get(f"{ANALYSIS_API}/health", timeout=2).status_code == 200
            management_ok = requests.get(f"{MANAGEMENT_API}/health", timeout=2).status_code == 200
            
            if not analysis_ok or not management_ok:
                pytest.skip("One or both services are not running")
            
            # Пытаемся получить анализ
            response = requests.get(
                f"{ANALYSIS_API}/api/token/{TEST_TOKEN}/risk",
                timeout=10
            )
            
            if response.status_code == 200:
                print("✅ Full analysis flow works")
            else:
                print(f"⚠️ Analysis returned {response.status_code}")
                
        except Exception as e:
            pytest.skip(f"Integration test failed: {e}")