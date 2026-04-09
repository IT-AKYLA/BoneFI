# import pytest
# from fastapi.testclient import TestClient
# from src.api.main import app

# client = TestClient(app)

# class TestAPI:
    
#     def test_health_check(self):
#         """Тест проверки здоровья"""
#         response = client.get("/health")
#         assert response.status_code == 200
#         assert response.json().get("status") == "ok"
    
#     def test_get_tokens(self):
#         """Тест получения списка токенов"""
#         response = client.get("/api/tokens?limit=10")
#         # Может быть пустым, но не должно падать
#         assert response.status_code in [200, 404]
    
#     def test_analyze_async(self):
#         """Тест асинхронного анализа"""
#         # Используем тестовый токен
#         response = client.get("/api/analyze/TestToken111?save_history=false")
        
#         # Должен вернуть task_id
#         if response.status_code == 200:
#             data = response.json()
#             assert "task_id" in data
#             assert data["status"] == "processing"
    
#     def test_revolutionary_score_endpoint(self):
#         """Тест эндпоинта революционного скора"""
#         response = client.get("/api/token/TestToken111/revolutionary/score")
        
#         if response.status_code == 200:
#             data = response.json()
#             assert "revolutionary_score" in data
#             assert "risk_level" in data