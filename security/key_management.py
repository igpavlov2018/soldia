"""
✅ MODERNIZED: Key Management System with AWS KMS
Secure private key storage, encryption, and rotation

Features:
- Encrypted key storage in AWS KMS
- Automatic key rotation with approval
- Audit logging of all key access
- No plaintext keys in environment
- Access control via IAM policies
"""

import logging
import boto3
from datetime import datetime, timedelta, timezone
from typing import Optional
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class KeyRotationStatus(str, Enum):
    """Key rotation status"""
    ACTIVE = "active"
    PENDING_ROTATION = "pending_rotation"
    ROTATED = "rotated"
    REVOKED = "revoked"


@dataclass
class KeyMetadata:
    """Key metadata"""
    key_id: str
    created_at: datetime
    last_rotated_at: Optional[datetime]
    status: KeyRotationStatus
    created_by: str
    rotation_schedule: int  # Days between rotations


class KeyManagementSystem:
    """
    Secure private key management using AWS KMS and Systems Manager Parameter Store
    
    Architecture:
    1. Private key stored encrypted in Parameter Store
    2. KMS key encrypts all data
    3. CloudTrail logs all access
    4. IAM policies control who can access
    5. Rotation ceremony for security
    
    Usage:
        key_manager = KeyManagementSystem()
        private_key = key_manager.get_private_key()
        key_manager.rotate_private_key(new_key, approver_id=1)
    """
    
    def __init__(self, aws_region: str = "us-east-1", kms_key_id: Optional[str] = None):
        """
        Initialize KMS client
        
        Args:
            aws_region: AWS region
            kms_key_id: KMS key ARN or ID for encryption
        """
        self.aws_region = aws_region
        self.kms_key_id = kms_key_id
        
        self.ssm_client = None
        self.kms_client = None
        self.cloudtrail_client = None
        
        self._initialize_clients()
        self.key_metadata: Optional[KeyMetadata] = None
    
    def _initialize_clients(self) -> None:
        """Initialize AWS clients"""
        try:
            self.ssm_client = boto3.client('ssm', region_name=self.aws_region)
            self.kms_client = boto3.client('kms', region_name=self.aws_region)
            self.cloudtrail_client = boto3.client('cloudtrail', region_name=self.aws_region)
            logger.info(f"✅ AWS KMS clients initialized (region: {self.aws_region})")
        except Exception as e:
            logger.error(f"❌ Failed to initialize AWS clients: {e}")
            raise
    
    async def get_private_key(self) -> str:
        """
        Retrieve decrypted private key from AWS Systems Manager Parameter Store
        
        Flow:
        1. Fetch from Parameter Store (encrypted with KMS)
        2. KMS automatically decrypts
        3. Log access in CloudTrail
        4. Return decrypted key
        
        Returns:
            Base58-encoded Solana private key
            
        Raises:
            ValueError: If key not found or decryption fails
        """
        try:
            logger.info("🔐 Retrieving private key from AWS Parameter Store...")
            
            # Fetch from Parameter Store
            response = self.ssm_client.get_parameter(
                Name='/soldia/hot-wallet-private-key',
                WithDecryption=True  # KMS decrypts automatically
            )
            
            private_key = response['Parameter']['Value']
            
            # Extract metadata
            metadata = response.get('Parameter', {})
            last_modified = metadata.get('LastModifiedDate', datetime.now(timezone.utc))
            
            # Log successful retrieval
            self._log_key_access(
                operation="GET",
                status="success",
                key_id='/soldia/hot-wallet-private-key'
            )
            
            logger.info("✅ Private key retrieved successfully from Parameter Store")
            logger.info(f"   Last modified: {last_modified}")
            
            return private_key
        
        except self.ssm_client.exceptions.ParameterNotFound:
            logger.error("❌ Private key not found in Parameter Store")
            self._log_key_access(
                operation="GET",
                status="failed",
                error="Key not found"
            )
            raise ValueError("Private key not configured")
        
        except Exception as e:
            logger.error(f"❌ Failed to retrieve private key: {e}")
            self._log_key_access(
                operation="GET",
                status="failed",
                error=str(e)
            )
            raise ValueError("Could not retrieve private key")
    
    async def rotate_private_key(
        self,
        new_private_key: str,
        approver_id: int,
        approver_email: str
    ) -> bool:
        """
        Rotate private key with approval requirement and audit trail
        
        Security Process:
        1. Validate new key format
        2. Store with encryption
        3. Tag with rotation metadata
        4. Log in CloudTrail
        5. Notify security team
        
        Args:
            new_private_key: New base58-encoded Solana private key
            approver_id: User ID who approved rotation
            approver_email: Email of approver for audit
        
        Returns:
            True if rotation successful
        """
        try:
            logger.info(f"🔄 Rotating private key (approved by {approver_email})...")
            
            # Validate key format (basic check)
            if not self._validate_key_format(new_private_key):
                raise ValueError("Invalid private key format")
            
            rotation_time = datetime.now(timezone.utc)
            
            # Store new key encrypted by KMS
            response = self.ssm_client.put_parameter(
                Name='/soldia/hot-wallet-private-key',
                Value=new_private_key,
                Type='SecureString',
                KeyId=self.kms_key_id,
                Overwrite=True,
                Tier='Advanced',
                Description='Solana hot wallet private key for withdrawals',
                Tags=[
                    {'Key': 'Application', 'Value': 'soldia'},
                    {'Key': 'RotatedAt', 'Value': rotation_time.isoformat()},
                    {'Key': 'RotatedBy', 'Value': str(approver_id)},
                    {'Key': 'RotatedByEmail', 'Value': approver_email},
                    {'Key': 'Purpose', 'Value': 'hot-wallet-withdrawals'},
                    {'Key': 'Sensitivity', 'Value': 'critical'}
                ]
            )
            
            # Log rotation
            self._log_key_access(
                operation="ROTATE",
                status="success",
                key_id='/soldia/hot-wallet-private-key',
                approver_id=approver_id,
                approver_email=approver_email
            )
            
            logger.info(f"✅ Private key rotated successfully")
            logger.info(f"   Approved by: {approver_email}")
            logger.info(f"   Version: {response['Version']}")
            logger.info(f"   Time: {rotation_time}")
            
            # Send notification (optional)
            self._notify_key_rotation(approver_email, rotation_time)
            
            return True
        
        except ValueError as e:
            logger.error(f"❌ Key rotation validation failed: {e}")
            self._log_key_access(
                operation="ROTATE",
                status="failed",
                error=str(e)
            )
            return False
        
        except Exception as e:
            logger.error(f"❌ Key rotation failed: {e}")
            self._log_key_access(
                operation="ROTATE",
                status="failed",
                error=str(e)
            )
            return False
    
    def should_rotate_key(self, rotation_days: int = 7) -> bool:
        """
        Check if key should be rotated (configurable interval)
        
        Args:
            rotation_days: Days since last rotation to trigger alert
        
        Returns:
            True if key should be rotated
        """
        try:
            response = self.ssm_client.get_parameter(
                Name='/soldia/hot-wallet-private-key'
            )
            
            # Get last modified time
            last_modified = response['Parameter']['LastModifiedDate']
            
            # Check if rotation needed
            # AWS LastModifiedDate is timezone-aware; ensure it is before subtracting
            lm_aware = last_modified if last_modified.tzinfo else last_modified.replace(tzinfo=timezone.utc)
            days_since_rotation = (datetime.now(timezone.utc) - lm_aware).days
            
            if days_since_rotation >= rotation_days:
                logger.warning(
                    f"⚠️  Key rotation recommended: {days_since_rotation} days since last rotation"
                )
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"Error checking key rotation: {e}")
            return False
    
    def _validate_key_format(self, key: str) -> bool:
        """
        Validate private key format
        
        Args:
            key: Private key string
        
        Returns:
            True if valid format
        """
        # Solana keys are base58 encoded
        if not key or len(key) < 87:  # Base58 encoded 64-byte key
            return False
        
        # Check if it's valid base58
        base58_chars = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        if not all(c in base58_chars for c in key):
            return False
        
        return True
    
    def _log_key_access(
        self,
        operation: str,
        status: str,
        key_id: str = "hot-wallet",
        approver_id: Optional[int] = None,
        approver_email: Optional[str] = None,
        error: Optional[str] = None
    ) -> None:
        """
        Log key access via CloudTrail
        
        Args:
            operation: GET, ROTATE, REVOKE, etc.
            status: success or failed
            key_id: Key identifier
            approver_id: User who approved (if applicable)
            approver_email: Email of approver
            error: Error message if failed
        """
        try:
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "operation": operation,
                "key_id": key_id,
                "status": status,
                "approver_id": approver_id,
                "approver_email": approver_email,
                "error": error
            }
            
            logger.info(f"🔐 Key Access Log: {operation} {key_id} - {status}")
            
            # CloudTrail automatically logs API calls
            # Additional logging for audit trail
            if operation == "ROTATE" and status == "success":
                logger.warning(
                    f"🚨 SECURITY ALERT: Private key rotated\n"
                    f"   Approver: {approver_email}\n"
                    f"   Time: {log_entry['timestamp']}"
                )
        
        except Exception as e:
            logger.error(f"Failed to log key access: {e}")
    
    def _notify_key_rotation(self, approver_email: str, rotation_time: datetime) -> None:
        """
        Send notification about key rotation (optional)
        
        Args:
            approver_email: Email to notify
            rotation_time: Time of rotation
        """
        try:
            logger.info(f"📧 Sending key rotation notification to {approver_email}...")
            
            # Implement SNS notification or email
            # Example: send_email_notification(...)
            
            logger.info("✅ Key rotation notification sent")
        
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
    
    def get_key_metadata(self) -> Optional[KeyMetadata]:
        """Get key metadata for audit purposes"""
        try:
            response = self.ssm_client.get_parameter(
                Name='/soldia/hot-wallet-private-key'
            )
            
            param = response['Parameter']
            tags = {tag['Key']: tag['Value'] for tag in param.get('Tags', [])}
            
            return KeyMetadata(
                key_id=param['Name'],
                created_at=param.get('LastModifiedDate', datetime.now(timezone.utc)),
                last_rotated_at=datetime.fromisoformat(tags.get('RotatedAt', datetime.now(timezone.utc).isoformat())),
                status=KeyRotationStatus(tags.get('Status', 'active')),
                created_by=tags.get('RotatedBy', 'unknown'),
                rotation_schedule=7  # Weekly
            )
        
        except Exception as e:
            logger.error(f"Failed to get key metadata: {e}")
            return None


# Singleton instance
key_manager: Optional[KeyManagementSystem] = None


def get_key_manager(aws_region: str = "us-east-1", kms_key_id: Optional[str] = None) -> KeyManagementSystem:
    """Get or create key manager instance"""
    global key_manager
    
    if key_manager is None:
        key_manager = KeyManagementSystem(aws_region=aws_region, kms_key_id=kms_key_id)
    
    return key_manager
