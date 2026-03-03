"""
profile_manager.py
==================
Manage user profiles that bundle together:
- API keys (Gemini, OpenAI, etc.)
- LinkedIn credentials
- Email configuration
- Resume
- Work preferences

Each profile is stored in data_folder/profiles/{profile_name}/
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
import shutil
from datetime import datetime

from src.logging import logger


PROFILES_DIR = Path("data_folder/profiles")
ACTIVE_PROFILE_FILE = Path("data_folder/.active_profile")


class Profile:
    """Represents a user profile with all associated data."""
    
    def __init__(self, name: str):
        self.name = name
        self.path = PROFILES_DIR / name
        
    def exists(self) -> bool:
        return self.path.exists()
    
    def create(self) -> None:
        """Create profile directory structure."""
        self.path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created profile: {self.name}")
    
    def delete(self) -> None:
        """Delete profile and all its data."""
        if self.path.exists():
            shutil.rmtree(self.path)
            logger.info(f"Deleted profile: {self.name}")
    
    def get_secrets_path(self) -> Path:
        return self.path / "secrets.yaml"
    
    def get_resume_path(self) -> Path:
        return self.path / "plain_text_resume.yaml"
    
    def get_email_config_path(self) -> Path:
        return self.path / "email_config.yaml"
    
    def get_work_prefs_path(self) -> Path:
        return self.path / "work_preferences.yaml"
    
    def get_metadata_path(self) -> Path:
        return self.path / "profile_metadata.yaml"
    
    def load_metadata(self) -> Dict[str, Any]:
        """Load profile metadata (creation date, description, etc.)."""
        meta_path = self.get_metadata_path()
        if not meta_path.exists():
            return {
                "name": self.name,
                "created_at": datetime.now().isoformat(),
                "description": ""
            }
        try:
            with open(meta_path, "r", encoding="utf-8") as fh:
                return yaml.safe_load(fh) or {}
        except Exception:
            return {}
    
    def save_metadata(self, metadata: Dict[str, Any]) -> None:
        """Save profile metadata."""
        self.path.mkdir(parents=True, exist_ok=True)
        with open(self.get_metadata_path(), "w", encoding="utf-8") as fh:
            yaml.safe_dump(metadata, fh, sort_keys=False)
    
    def to_dict(self) -> Dict[str, Any]:
        """Return profile summary for API responses."""
        metadata = self.load_metadata()
        
        has_api_key = False
        has_linkedin = False
        has_resume = False
        has_email = False
        
        secrets_path = self.get_secrets_path()
        if secrets_path.exists():
            try:
                with open(secrets_path, "r", encoding="utf-8") as fh:
                    secrets = yaml.safe_load(fh) or {}
                    # Check for any API key
                    for key in ["gemini_api_key", "openai_api_key", "claude_api_key", "llm_api_key"]:
                        if secrets.get(key, "").strip():
                            has_api_key = True
                            break
                    # Check for LinkedIn credentials
                    has_linkedin = bool(secrets.get("linkedin_email", "").strip())
            except Exception:
                pass
        
        has_resume = self.get_resume_path().exists()
        has_email = self.get_email_config_path().exists()
        
        return {
            "name": self.name,
            "description": metadata.get("description", ""),
            "created_at": metadata.get("created_at", ""),
            "has_api_key": has_api_key,
            "has_linkedin": has_linkedin,
            "has_resume": has_resume,
            "has_email": has_email,
            "is_complete": has_api_key and has_linkedin and has_resume
        }


class ProfileManager:
    """Manages user profiles and profile switching."""
    
    @staticmethod
    def list_profiles() -> List[Profile]:
        """Return all available profiles."""
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        profiles = []
        for p in PROFILES_DIR.iterdir():
            if p.is_dir():
                profiles.append(Profile(p.name))
        return sorted(profiles, key=lambda x: x.name)
    
    @staticmethod
    def get_active_profile() -> Optional[str]:
        """Get the name of the currently active profile."""
        if ACTIVE_PROFILE_FILE.exists():
            try:
                return ACTIVE_PROFILE_FILE.read_text().strip()
            except Exception:
                return None
        return None
    
    @staticmethod
    def set_active_profile(profile_name: str) -> None:
        """Set the active profile and copy its files to data_folder."""
        profile = Profile(profile_name)
        if not profile.exists():
            raise ValueError(f"Profile '{profile_name}' does not exist")
        
        # Save active profile marker
        ACTIVE_PROFILE_FILE.write_text(profile_name)
        
        # Copy profile files to data_folder
        data_folder = Path("data_folder")
        
        # Copy secrets
        if profile.get_secrets_path().exists():
            shutil.copy2(profile.get_secrets_path(), data_folder / "secrets.yaml")
        
        # Copy resume
        if profile.get_resume_path().exists():
            shutil.copy2(profile.get_resume_path(), data_folder / "plain_text_resume.yaml")
        
        # Copy email config
        if profile.get_email_config_path().exists():
            shutil.copy2(profile.get_email_config_path(), data_folder / "email_config.yaml")
        
        # Copy work preferences (if exists)
        if profile.get_work_prefs_path().exists():
            shutil.copy2(profile.get_work_prefs_path(), data_folder / "work_preferences.yaml")
        
        logger.info(f"Activated profile: {profile_name}")
    
    @staticmethod
    def save_current_to_profile(profile_name: str, description: str = "") -> Profile:
        """Save current data_folder contents to a profile."""
        profile = Profile(profile_name)
        profile.create()
        
        data_folder = Path("data_folder")
        
        # Copy current files to profile
        files_to_copy = [
            ("secrets.yaml", profile.get_secrets_path()),
            ("plain_text_resume.yaml", profile.get_resume_path()),
            ("email_config.yaml", profile.get_email_config_path()),
            ("work_preferences.yaml", profile.get_work_prefs_path()),
        ]
        
        for src_name, dest_path in files_to_copy:
            src_path = data_folder / src_name
            if src_path.exists():
                shutil.copy2(src_path, dest_path)
        
        # Save metadata
        metadata = {
            "name": profile_name,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        profile.save_metadata(metadata)
        
        # Mark as active
        ACTIVE_PROFILE_FILE.write_text(profile_name)
        
        logger.info(f"Saved current configuration to profile: {profile_name}")
        return profile
    
    @staticmethod
    def create_profile(profile_name: str, description: str = "") -> Profile:
        """Create a new empty profile."""
        profile = Profile(profile_name)
        if profile.exists():
            raise ValueError(f"Profile '{profile_name}' already exists")
        
        profile.create()
        
        # Initialize with empty/default files
        profile.get_secrets_path().write_text("# API keys and credentials\n")
        
        # Copy default work_preferences if it exists
        default_prefs = Path("data_folder_example/work_preferences.yaml")
        if default_prefs.exists():
            shutil.copy2(default_prefs, profile.get_work_prefs_path())
        
        metadata = {
            "name": profile_name,
            "description": description,
            "created_at": datetime.now().isoformat()
        }
        profile.save_metadata(metadata)
        
        logger.info(f"Created new profile: {profile_name}")
        return profile
