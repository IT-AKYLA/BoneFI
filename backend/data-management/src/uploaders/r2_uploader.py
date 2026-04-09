import boto3
import gzip
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY", "")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY", "")
R2_BUCKET = os.getenv("R2_BUCKET", "solana-data")
R2_ENDPOINT = os.getenv("R2_ENDPOINT", "")


class R2Uploader:
    def __init__(self):
        self.enabled = bool(R2_ACCESS_KEY and R2_SECRET_KEY and R2_ENDPOINT)
        
        if self.enabled:
            self.client = boto3.client(
                's3',
                endpoint_url=R2_ENDPOINT,
                aws_access_key_id=R2_ACCESS_KEY,
                aws_secret_access_key=R2_SECRET_KEY,
                region_name='auto'
            )
            self.bucket = R2_BUCKET

    def upload_token_data(self, token_mint: str, data: Dict) -> bool:
        if not self.enabled:
            return False
        
        try:
            json_str = json.dumps(data, default=str)
            compressed = gzip.compress(json_str.encode('utf-8'))
            
            timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
            key = f"{token_mint}/{timestamp}.json.gz"
            
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=compressed,
                ContentType='application/json',
                ContentEncoding='gzip'
            )
            
            return True
            
        except Exception as e:
            print(f"R2 upload failed for {token_mint}: {e}")
            return False

    def upload_backup(self, token_mint: str, data: Dict) -> bool:
        return self.upload_token_data(token_mint, data)

    def file_exists(self, token_mint: str, filename: str) -> bool:
        if not self.enabled:
            return False
        
        try:
            key = f"{token_mint}/{filename}"
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False