"""Tests for server lifecycle management"""
import pytest
import time
import urllib.request
import urllib.error

# app.main imports rumps at module level (macOS only)
pytest.importorskip("rumps")


class TestUvicornServer:
    """Tests for UvicornServer class"""

    def test_server_starts_and_responds(self):
        """Server should start and respond to health check"""
        from run_app import app as fastapi_app
        from app.main import UvicornServer

        # Use unique port to avoid conflicts
        server = UvicornServer(app=fastapi_app, port=18765)
        server.start()

        try:
            # Wait for startup with timeout
            assert server.wait_for_startup(timeout=10) is True

            # Verify health endpoint responds
            resp = urllib.request.urlopen("http://127.0.0.1:18765/health", timeout=5)
            assert resp.status == 200
            data = resp.read().decode('utf-8')
            assert 'healthy' in data

        finally:
            server.shutdown()

    def test_server_shutdown_is_clean(self):
        """Server should shut down cleanly"""
        from run_app import app as fastapi_app
        from app.main import UvicornServer

        server = UvicornServer(app=fastapi_app, port=18766)
        server.start()

        # Wait for startup
        assert server.wait_for_startup(timeout=10) is True

        # Shutdown
        server.shutdown()
        time.sleep(1)

        # Thread should have stopped
        assert not server._thread.is_alive()

    def test_server_startup_timeout(self):
        """Should timeout if server doesn't start"""
        from run_app import app as fastapi_app
        from app.main import UvicornServer

        # Create server but don't start it
        server = UvicornServer(app=fastapi_app, port=18767)

        # Should timeout immediately (server not started)
        assert server.wait_for_startup(timeout=1) is False

    def test_server_uses_correct_port(self):
        """Server should bind to specified port"""
        from run_app import app as fastapi_app
        from app.main import UvicornServer

        custom_port = 18768
        server = UvicornServer(app=fastapi_app, port=custom_port)
        server.start()

        try:
            assert server.wait_for_startup(timeout=10) is True

            # Verify server is on correct port
            resp = urllib.request.urlopen(f"http://127.0.0.1:{custom_port}/health", timeout=5)
            assert resp.status == 200

            # Wrong port should fail
            with pytest.raises(urllib.error.URLError):
                urllib.request.urlopen(f"http://127.0.0.1:{custom_port + 1}/health", timeout=2)

        finally:
            server.shutdown()

    def test_multiple_servers_different_ports(self):
        """Should be able to run multiple servers on different ports"""
        from run_app import app as fastapi_app
        from app.main import UvicornServer

        server1 = UvicornServer(app=fastapi_app, port=18769)
        server2 = UvicornServer(app=fastapi_app, port=18770)

        try:
            server1.start()
            server2.start()

            assert server1.wait_for_startup(timeout=10) is True
            assert server2.wait_for_startup(timeout=10) is True

            # Both should respond
            resp1 = urllib.request.urlopen("http://127.0.0.1:18769/health", timeout=5)
            resp2 = urllib.request.urlopen("http://127.0.0.1:18770/health", timeout=5)

            assert resp1.status == 200
            assert resp2.status == 200

        finally:
            server1.shutdown()
            server2.shutdown()
