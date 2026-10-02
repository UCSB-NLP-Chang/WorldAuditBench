#!/usr/bin/env python3
"""Publish Subway together with the current indoor and U018 review catalog."""
import subprocess
subprocess.run(['python3','/home/ubuntu/unreal-auditor/review-service/releases/public-20260911/publish.py'],check=True)
