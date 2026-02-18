#!/usr/bin/env python3
"""
Test script for HMAC-signed webhook requests.
Usage: python scripts/test_hmac_webhook.py
"""
import hmac
import hashlib
import time
import json
import sys
import argparse
import requests


def generate_hmac_signature(secret: str, timestamp: str, nonce: str, body: bytes) -> str:
    """Generate HMAC-SHA256 signature for webhook request."""
    message = f"{timestamp}.{nonce}.".encode('utf-8') + body
    signature = hmac.new(secret.encode('utf-8'), message, hashlib.sha256).hexdigest()
    return signature


def send_webhook_request(
    url: str,
    secret: str,
    symbol: str = "BTCUSDT",
    side: str = "long",
    confidence: float = 0.95,
    use_hmac: bool = True
):
    """Send a webhook request with optional HMAC authentication."""
    
    # Generate timestamp and nonce
    timestamp = int(time.time())
    nonce = f"test_{int(time.time() * 1000000)}"
    
    # Create payload
    payload = {
        "symbol": symbol,
        "timeframe": "5m",
        "side": side,
        "setup_id": "test_hmac",
        "confidence": confidence,
        "price": 40000.0,
        "event_time": str(int(time.time() * 1000)),
        "secret": secret,
        "timestamp": timestamp,
        "nonce": nonce
    }
    
    # Convert to JSON bytes
    body = json.dumps(payload).encode('utf-8')
    
    # Prepare headers
    headers = {
        "Content-Type": "application/json"
    }
    
    if use_hmac:
        # Generate HMAC signature
        signature = generate_hmac_signature(secret, str(timestamp), nonce, body)
        
        # Add HMAC headers
        headers["X-TV-Timestamp"] = str(timestamp)
        headers["X-TV-Nonce"] = nonce
        headers["X-TV-Signature"] = signature
        
        print(f"🔐 HMAC Authentication:")
        print(f"  Timestamp: {timestamp}")
        print(f"  Nonce: {nonce}")
        print(f"  Signature: {signature[:32]}...")
    else:
        print("🔓 Legacy Authentication (secret only)")
    
    print(f"\n📤 Sending request to {url}...")
    print(f"  Symbol: {symbol}")
    print(f"  Side: {side}")
    print(f"  Confidence: {confidence}")
    
    try:
        response = requests.post(url, data=body, headers=headers, timeout=10)
        
        print(f"\n📥 Response:")
        print(f"  Status: {response.status_code}")
        print(f"  Body: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("\n✅ Success!")
        elif response.status_code == 429:
            retry_after = response.headers.get('Retry-After', 'unknown')
            print(f"\n⚠️  Rate limited. Retry after {retry_after}s")
        elif response.status_code == 401:
            print("\n❌ Authentication failed!")
        elif response.status_code == 409:
            print("\n⚠️  Replay detected (nonce already used)")
        else:
            print(f"\n❌ Request failed!")
        
        return response.status_code == 200
        
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test HMAC-signed webhook requests")
    parser.add_argument("--url", default="http://localhost:8000/tv/webhook", 
                       help="Webhook URL")
    parser.add_argument("--secret", default="your_webhook_secret_here",
                       help="Webhook secret")
    parser.add_argument("--symbol", default="BTCUSDT",
                       help="Trading symbol")
    parser.add_argument("--side", choices=["long", "short"], default="long",
                       help="Trade side")
    parser.add_argument("--confidence", type=float, default=0.95,
                       help="Signal confidence (0-1)")
    parser.add_argument("--no-hmac", action="store_true",
                       help="Send without HMAC headers (legacy mode)")
    parser.add_argument("--count", type=int, default=1,
                       help="Number of requests to send")
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("🧪 HMAC Webhook Test Script")
    print("=" * 70)
    
    use_hmac = not args.no_hmac
    
    success_count = 0
    for i in range(args.count):
        if args.count > 1:
            print(f"\n--- Request {i+1}/{args.count} ---")
        
        success = send_webhook_request(
            url=args.url,
            secret=args.secret,
            symbol=args.symbol,
            side=args.side,
            confidence=args.confidence,
            use_hmac=use_hmac
        )
        
        if success:
            success_count += 1
        
        if i < args.count - 1:
            time.sleep(0.5)  # Small delay between requests
    
    if args.count > 1:
        print(f"\n" + "=" * 70)
        print(f"📊 Summary: {success_count}/{args.count} requests successful")
        print("=" * 70)
    
    return 0 if success_count == args.count else 1


if __name__ == "__main__":
    sys.exit(main())
