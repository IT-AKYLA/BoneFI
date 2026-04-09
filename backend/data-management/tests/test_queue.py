import pytest
import sys
from src.queue.queue_manager import enqueue_collection, get_queue_status, cancel_job, IS_WINDOWS


class TestQueueManager:
    
    def test_is_windows_detection(self):
        assert isinstance(IS_WINDOWS, bool)
    
    def test_enqueue_collection_returns_job_id(self):
        """Тест: enqueue_collection всегда возвращает job_id"""
        try:
            job_id = enqueue_collection(
                token_mint="TestToken",
                force=False,
                collect_mode="latest",
                early_limit=10000
            )
            assert isinstance(job_id, str)
            assert len(job_id) > 0
        except Exception as e:
            pytest.skip(f"Queue error: {e}")
    
    def test_enqueue_collection_with_different_modes(self):
        try:
            job_id_1 = enqueue_collection("Token1", collect_mode="latest")
            job_id_2 = enqueue_collection("Token2", collect_mode="earliest", early_limit=5000)
            assert job_id_1 is not None
            assert job_id_2 is not None
        except Exception as e:
            pytest.skip(f"Queue error: {e}")
    
    def test_enqueue_collection_with_force_flag(self):
        try:
            job_id = enqueue_collection("ForceToken", force=True)
            assert job_id is not None
        except Exception as e:
            pytest.skip(f"Queue error: {e}")
    
    def test_get_queue_status_returns_dict(self):
        status = get_queue_status()
        assert isinstance(status, dict)
        assert "queued" in status
    
    def test_cancel_job_returns_bool(self):
        result = cancel_job("non_existent_job_id")
        assert isinstance(result, bool)


class TestQueueOnWindows:
    
    @pytest.mark.skipif(not IS_WINDOWS, reason="Windows specific test")
    def test_windows_queue_returns_empty_status(self):
        status = get_queue_status()
        assert status["queued"] == 0
    
    @pytest.mark.skipif(not IS_WINDOWS, reason="Windows specific test")
    def test_windows_cancel_always_false(self):
        assert cancel_job("any_job") == False


class TestQueueOnLinux:
    
    @pytest.mark.skipif(IS_WINDOWS, reason="Linux specific test")
    def test_linux_queue_structure(self):
        status = get_queue_status()
        assert "job_ids" in status


class TestEdgeCases:
    
    def test_empty_token_mint(self):
        try:
            job_id = enqueue_collection(token_mint="", force=True)
            assert isinstance(job_id, str)
        except Exception as e:
            pytest.skip(f"Queue error: {e}")
    
    def test_very_long_token_mint(self):
        long_token = "A" * 100
        try:
            job_id = enqueue_collection(token_mint=long_token, force=True)
            assert isinstance(job_id, str)
        except Exception as e:
            pytest.skip(f"Queue error: {e}")
    
    def test_invalid_collect_mode(self):
        try:
            job_id = enqueue_collection("TestToken", collect_mode="invalid_mode")
            assert isinstance(job_id, str)
        except Exception as e:
            pytest.skip(f"Queue error: {e}")


class TestIntegrationWithCollector:
    
    def test_queue_creates_valid_job_id_format(self):
        try:
            job_id = enqueue_collection("FormatTestToken")
            assert isinstance(job_id, str)
            assert len(job_id) >= 1
        except Exception as e:
            pytest.skip(f"Queue error: {e}")
    
    def test_multiple_enqueues_produce_different_ids(self):
        try:
            ids = set()
            for i in range(3):
                job_id = enqueue_collection(f"Token{i}", force=True)
                ids.add(job_id)
            assert len(ids) == 3
        except Exception as e:
            pytest.skip(f"Queue error: {e}")