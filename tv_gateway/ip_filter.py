"""
IP filtering with CIDR support for allowlist/denylist.
Handles X-Forwarded-For with trusted proxy validation.
"""
import ipaddress
from typing import List, Optional, Tuple, Union
import logging

logger = logging.getLogger(__name__)


class IPFilter:
    """IP-based access control with CIDR support."""
    
    def __init__(
        self,
        allowlist: Optional[List[str]] = None,
        denylist: Optional[List[str]] = None,
        trusted_proxies: Optional[List[str]] = None
    ):
        """
        Initialize IP filter.
        
        Args:
            allowlist: List of allowed CIDR ranges (None = allow all)
            denylist: List of denied CIDR ranges
            trusted_proxies: List of trusted proxy CIDR ranges
        """
        self.allowlist = self._parse_cidrs(allowlist or [])
        self.denylist = self._parse_cidrs(denylist or [])
        self.trusted_proxies = self._parse_cidrs(trusted_proxies or [])
        
        logger.info(
            f"IPFilter initialized: "
            f"allowlist={len(self.allowlist)}, "
            f"denylist={len(self.denylist)}, "
            f"trusted_proxies={len(self.trusted_proxies)}"
        )
    
    def _parse_cidrs(self, cidr_list: List[str]) -> List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]:
        """Parse CIDR strings into network objects."""
        networks = []
        
        for cidr in cidr_list:
            cidr = cidr.strip()
            if not cidr:
                continue
            
            try:
                # Handle single IPs without /32
                if '/' not in cidr:
                    cidr = f"{cidr}/32"
                
                network = ipaddress.ip_network(cidr, strict=False)
                networks.append(network)
            except ValueError as e:
                logger.error(f"Invalid CIDR: {cidr}: {e}")
        
        return networks
    
    def _ip_in_networks(
        self,
        ip: str,
        networks: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]]
    ) -> bool:
        """Check if IP is in any of the networks."""
        try:
            ip_obj = ipaddress.ip_address(ip)
            
            for network in networks:
                if ip_obj in network:
                    return True
            
            return False
        
        except ValueError:
            logger.warning(f"Invalid IP address: {ip}")
            return False
    
    def extract_client_ip(
        self,
        direct_ip: str,
        forwarded_for: Optional[str] = None
    ) -> str:
        """
        Extract real client IP, considering X-Forwarded-For if from trusted proxy.
        
        Args:
            direct_ip: Direct connection IP
            forwarded_for: X-Forwarded-For header value
            
        Returns:
            Real client IP
        """
        # If no forwarded header, use direct IP
        if not forwarded_for:
            return direct_ip
        
        # Only trust X-Forwarded-For if request comes from trusted proxy
        if not self.trusted_proxies:
            # No trusted proxies configured - don't trust forwarded headers
            logger.debug(f"Ignoring X-Forwarded-For from untrusted source: {direct_ip}")
            return direct_ip
        
        # Check if direct IP is trusted proxy
        if not self._ip_in_networks(direct_ip, self.trusted_proxies):
            logger.warning(
                f"Ignoring X-Forwarded-For from non-trusted proxy: {direct_ip}"
            )
            return direct_ip
        
        # Parse X-Forwarded-For (format: "client, proxy1, proxy2")
        # Take the leftmost IP (original client)
        ips = [ip.strip() for ip in forwarded_for.split(',')]
        if ips:
            client_ip = ips[0]
            logger.debug(f"Using client IP from X-Forwarded-For: {client_ip}")
            return client_ip
        
        return direct_ip
    
    def is_allowed(self, client_ip: str) -> Tuple[bool, Optional[str]]:
        """
        Check if IP is allowed.
        
        Args:
            client_ip: Client IP address
            
        Returns:
            Tuple of (is_allowed, reason)
        """
        # Check denylist first
        if self.denylist and self._ip_in_networks(client_ip, self.denylist):
            reason = f"IP {client_ip} is in denylist"
            logger.warning(reason)
            return False, reason
        
        # Check allowlist (if configured)
        if self.allowlist:
            if self._ip_in_networks(client_ip, self.allowlist):
                return True, None
            else:
                reason = f"IP {client_ip} not in allowlist"
                logger.warning(reason)
                return False, reason
        
        # No allowlist configured - allow by default
        return True, None
    
    def get_stats(self) -> dict:
        """Get IP filter statistics."""
        return {
            "allowlist_rules": len(self.allowlist),
            "denylist_rules": len(self.denylist),
            "trusted_proxies": len(self.trusted_proxies),
            "allowlist_cidrs": [str(n) for n in self.allowlist] if self.allowlist else None,
            "denylist_cidrs": [str(n) for n in self.denylist] if self.denylist else None,
        }
