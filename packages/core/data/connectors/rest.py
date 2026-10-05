import httpx
from typing import Dict, Any, Optional
from urllib.parse import urlparse
import ipaddress
import socket
import os
from packages.core.data.connectors.base import DataConnector

class SecurityError(Exception):
    pass

class RESTConnector(DataConnector):
    def get_connector_type(self) -> str:
        return "REST"
        
    def _validate_url_ssrf(self, url_str: str):
        parsed = urlparse(url_str)
        if parsed.scheme not in ["http", "https"]:
            raise SecurityError(f"Unsupported scheme: {parsed.scheme}. Only http/https are allowed.")
            
        hostname = parsed.hostname
        if not hostname:
            raise SecurityError("Invalid URL format.")
            
        try:
            ip = socket.gethostbyname(hostname)
            ip_obj = ipaddress.ip_address(ip)
            if ip_obj.is_loopback or ip_obj.is_private or ip_obj.is_link_local or ip_obj.is_reserved:
                # Security hardening: never allow bypass in production
                is_prod = os.environ.get("ENVIRONMENT", "development").lower() == "production"
                if is_prod:
                    raise SecurityError(f"Target resolves to unsafe internal IP: {ip}. Bypass forbidden in production.")
                    
                allow_local = os.environ.get("ALLOW_LOCAL_REST") == "1"
                if not allow_local:
                    raise SecurityError(f"Target resolves to unsafe internal IP: {ip}")
        except Exception as e:
            if isinstance(e, SecurityError):
                raise
            raise SecurityError(f"DNS resolution failed: {e}")

    def validate_config(self, config: Dict[str, Any]) -> bool:
        url = config.get("url")
        if not url:
            return False
        self._validate_url_ssrf(url)
        return True

    def fetch(self, config: Dict[str, Any], checkpoint: Optional[Dict[str, Any]] = None) -> Any:
        url = config.get("url")
        method = config.get("method", "GET")
        headers = config.get("headers", {})
        params = config.get("params", {})
        timeout = config.get("timeout", 10.0)
        
        self._validate_url_ssrf(url)
        
        if checkpoint and checkpoint.get("last_successful_cursor"):
            params["cursor"] = checkpoint["last_successful_cursor"]

        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            resp = client.request(method, url, headers=headers, params=params)
            
            if resp.is_redirect:
                loc = resp.headers.get("location")
                if loc:
                    self._validate_url_ssrf(loc)
                    resp = client.request(method, loc, headers=headers, params=params)
                    
            if resp.status_code >= 400:
                raise Exception(f"HTTP Error {resp.status_code}: {resp.text[:100]}")
                
            content = resp.read()
            if len(content) > config.get("max_size", 50 * 1024 * 1024):
                raise SecurityError("Response size limit exceeded")
                
            return content
