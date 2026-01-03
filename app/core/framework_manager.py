"""
Framework Manager for macOS Mod Manager

Manages installation and updates of macOS-ported mod frameworks:
- RED4ext (mod loader)
- TweakXL (tweak system)
- ArchiveXL (archive loading)

These frameworks have been ported to macOS from Windows and are available
from the memaxo GitHub repositories.
"""

import asyncio
import aiohttp
import aiofiles
import zipfile
import tempfile
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any, TypedDict, Literal, Callable
from dataclasses import dataclass, field
from datetime import datetime
from app.config import settings
from app.core.game_detector import detect_game_installations


class FrameworkConfig(TypedDict):
    repo: str
    asset_pattern: str
    install_path: str
    required_files: List[str]
    optional_files: List[str]
    description: str


@dataclass
class FrameworkStatus:
    name: str
    installed: bool
    version: Optional[str] = None
    latest_version: Optional[str] = None
    update_available: bool = False
    install_path: Optional[Path] = None
    healthy: bool = True
    missing_files: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class InstallResult:
    success: bool
    framework: str
    version: Optional[str] = None
    message: str = ""
    installed_files: List[str] = field(default_factory=list)


@dataclass
class GitHubRelease:
    tag_name: str
    name: str
    published_at: str
    assets: List[Dict[str, Any]]
    body: str


class FrameworkManager:
    """Manages RED4ext, TweakXL, ArchiveXL installations for macOS"""
    
    FRAMEWORKS: Dict[str, FrameworkConfig] = {
        'red4ext': {
            'repo': 'memaxo/RED4ext-macos',
            'asset_pattern': 'RED4ext',
            'install_path': 'red4ext',
            'required_files': ['RED4ext.dylib'],
            'optional_files': ['FridaGadget.dylib', 'config.ini'],
            'description': 'Native code mod loader for Cyberpunk 2077',
        },
        'tweakxl': {
            'repo': 'memaxo/cp2077-tweak-xl-macos',
            'asset_pattern': 'TweakXL',
            'install_path': 'red4ext/plugins/TweakXL',
            'required_files': ['TweakXL.dylib'],
            'optional_files': [],
            'description': 'TweakDB modification framework',
        },
        'archivexl': {
            'repo': 'memaxo/cp2077-archive-xl-macos',
            'asset_pattern': 'ArchiveXL',
            'install_path': 'red4ext/plugins/ArchiveXL',
            'required_files': ['ArchiveXL.dylib'],
            'optional_files': [],
            'description': 'Archive loading extension',
        },
    }
    
    def __init__(self, game_path: Optional[Path] = None):
        self.game_path = game_path
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={'Accept': 'application/vnd.github.v3+json'}
            )
        return self._session
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def _get_game_path(self) -> Path:
        if self.game_path:
            return self.game_path
        
        installations = await detect_game_installations()
        if not installations:
            raise RuntimeError("Cyberpunk 2077 installation not found")
        
        self.game_path = Path(installations[0]['path'])
        return self.game_path
    
    async def get_latest_release(self, repo: str) -> Optional[GitHubRelease]:
        """Get latest release from GitHub repository"""
        session = await self._get_session()
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return GitHubRelease(
                        tag_name=data['tag_name'],
                        name=data['name'],
                        published_at=data['published_at'],
                        assets=data['assets'],
                        body=data.get('body', ''),
                    )
                elif response.status == 404:
                    # No releases yet
                    return None
                else:
                    return None
        except Exception as e:
            print(f"Error fetching release from {repo}: {e}")
            return None
    
    async def get_all_releases(self, repo: str) -> List[GitHubRelease]:
        """Get all releases from GitHub repository"""
        session = await self._get_session()
        url = f"https://api.github.com/repos/{repo}/releases"
        
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return [
                        GitHubRelease(
                            tag_name=r['tag_name'],
                            name=r['name'],
                            published_at=r['published_at'],
                            assets=r['assets'],
                            body=r.get('body', ''),
                        )
                        for r in data
                    ]
        except Exception:
            pass
        return []
    
    async def check_status(self, framework_name: str) -> FrameworkStatus:
        """Check installation status of a framework"""
        if framework_name not in self.FRAMEWORKS:
            return FrameworkStatus(
                name=framework_name,
                installed=False,
                error=f"Unknown framework: {framework_name}"
            )
        
        config = self.FRAMEWORKS[framework_name]
        game_path = await self._get_game_path()
        install_path = game_path / config['install_path']
        
        # Check if installed
        installed = install_path.exists()
        missing_files = []
        
        if installed:
            for required_file in config['required_files']:
                file_path = install_path / required_file
                if not file_path.exists():
                    missing_files.append(required_file)
                    installed = False
        
        # Get installed version (try to read from version file or dylib)
        installed_version = None
        if installed:
            version_file = install_path / "version.txt"
            if version_file.exists():
                installed_version = version_file.read_text().strip()
        
        # Get latest version from GitHub
        latest_version = None
        release = await self.get_latest_release(config['repo'])
        if release:
            latest_version = release.tag_name.lstrip('v')
        
        # Check if update available
        update_available = False
        if installed_version and latest_version:
            update_available = installed_version != latest_version
        
        return FrameworkStatus(
            name=framework_name,
            installed=installed,
            version=installed_version,
            latest_version=latest_version,
            update_available=update_available,
            install_path=install_path if installed else None,
            healthy=installed and len(missing_files) == 0,
            missing_files=missing_files,
        )
    
    async def check_all_status(self) -> Dict[str, FrameworkStatus]:
        """Check status of all frameworks"""
        statuses = {}
        for name in self.FRAMEWORKS:
            statuses[name] = await self.check_status(name)
        return statuses
    
    async def install(
        self, 
        framework_name: str, 
        version: str = 'latest'
    ) -> InstallResult:
        """Install a framework from GitHub releases"""
        if framework_name not in self.FRAMEWORKS:
            return InstallResult(
                success=False,
                framework=framework_name,
                message=f"Unknown framework: {framework_name}"
            )
        
        config = self.FRAMEWORKS[framework_name]
        game_path = await self._get_game_path()
        install_path = game_path / config['install_path']
        
        # Get release
        if version == 'latest':
            release = await self.get_latest_release(config['repo'])
        else:
            releases = await self.get_all_releases(config['repo'])
            release = next(
                (r for r in releases if r.tag_name == version or r.tag_name == f'v{version}'),
                None
            )
        
        if not release:
            return InstallResult(
                success=False,
                framework=framework_name,
                message=f"No release found for {framework_name}"
            )
        
        # Find asset to download
        asset = None
        for a in release.assets:
            if config['asset_pattern'] in a['name'] and a['name'].endswith('.zip'):
                asset = a
                break
        
        if not asset:
            # Try to find any .dylib or .zip
            for a in release.assets:
                if a['name'].endswith('.dylib') or a['name'].endswith('.zip'):
                    asset = a
                    break
        
        if not asset:
            return InstallResult(
                success=False,
                framework=framework_name,
                message=f"No downloadable asset found for {framework_name}"
            )
        
        # Download and install
        session = await self._get_session()
        
        try:
            async with session.get(asset['browser_download_url']) as response:
                if response.status != 200:
                    return InstallResult(
                        success=False,
                        framework=framework_name,
                        message=f"Failed to download: HTTP {response.status}"
                    )
                
                # Create install directory
                install_path.mkdir(parents=True, exist_ok=True)
                
                content = await response.read()
                
                installed_files = []
                
                if asset['name'].endswith('.zip'):
                    # Extract ZIP
                    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
                        tmp.write(content)
                        tmp_path = tmp.name
                    
                    try:
                        with zipfile.ZipFile(tmp_path, 'r') as zf:
                            zf.extractall(install_path)
                            installed_files = zf.namelist()
                    finally:
                        Path(tmp_path).unlink()
                else:
                    # Direct file (e.g., .dylib)
                    dest_file = install_path / asset['name']
                    async with aiofiles.open(dest_file, 'wb') as f:
                        await f.write(content)
                    installed_files = [asset['name']]
                
                # Write version file
                version_file = install_path / "version.txt"
                async with aiofiles.open(version_file, 'w') as f:
                    await f.write(release.tag_name.lstrip('v'))
                
                return InstallResult(
                    success=True,
                    framework=framework_name,
                    version=release.tag_name,
                    message=f"Successfully installed {framework_name} {release.tag_name}",
                    installed_files=installed_files
                )
                
        except Exception as e:
            return InstallResult(
                success=False,
                framework=framework_name,
                message=f"Installation failed: {str(e)}"
            )
    
    async def update(self, framework_name: str) -> InstallResult:
        """Update framework to latest version"""
        status = await self.check_status(framework_name)
        
        if not status.installed:
            return await self.install(framework_name)
        
        if not status.update_available:
            return InstallResult(
                success=True,
                framework=framework_name,
                version=status.version,
                message=f"{framework_name} is already up to date"
            )
        
        # Backup existing installation
        game_path = await self._get_game_path()
        config = self.FRAMEWORKS[framework_name]
        install_path = game_path / config['install_path']
        backup_path = install_path.with_suffix('.backup')
        
        if backup_path.exists():
            shutil.rmtree(backup_path)
        
        if install_path.exists():
            shutil.copytree(install_path, backup_path)
        
        try:
            result = await self.install(framework_name, 'latest')
            
            if result.success:
                # Clean up backup
                if backup_path.exists():
                    shutil.rmtree(backup_path)
            else:
                # Restore backup
                if backup_path.exists():
                    if install_path.exists():
                        shutil.rmtree(install_path)
                    shutil.move(backup_path, install_path)
            
            return result
            
        except Exception as e:
            # Restore backup on error
            if backup_path.exists():
                if install_path.exists():
                    shutil.rmtree(install_path)
                shutil.move(backup_path, install_path)
            
            return InstallResult(
                success=False,
                framework=framework_name,
                message=f"Update failed: {str(e)}"
            )
    
    async def verify_integrity(self, framework_name: str) -> FrameworkStatus:
        """Verify framework installation integrity"""
        status = await self.check_status(framework_name)
        
        if not status.installed:
            status.healthy = False
            status.error = "Framework not installed"
            return status
        
        config = self.FRAMEWORKS[framework_name]
        
        # Check all required files
        for required_file in config['required_files']:
            file_path = status.install_path / required_file
            if not file_path.exists():
                status.missing_files.append(required_file)
                status.healthy = False
            elif file_path.suffix == '.dylib':
                # Verify dylib is loadable (basic check)
                if file_path.stat().st_size < 1000:
                    status.error = f"{required_file} appears corrupted (too small)"
                    status.healthy = False
        
        return status
    
    async def uninstall(self, framework_name: str) -> InstallResult:
        """Uninstall a framework"""
        if framework_name not in self.FRAMEWORKS:
            return InstallResult(
                success=False,
                framework=framework_name,
                message=f"Unknown framework: {framework_name}"
            )
        
        config = self.FRAMEWORKS[framework_name]
        game_path = await self._get_game_path()
        install_path = game_path / config['install_path']
        
        if not install_path.exists():
            return InstallResult(
                success=True,
                framework=framework_name,
                message=f"{framework_name} is not installed"
            )
        
        try:
            shutil.rmtree(install_path)
            return InstallResult(
                success=True,
                framework=framework_name,
                message=f"Successfully uninstalled {framework_name}"
            )
        except Exception as e:
            return InstallResult(
                success=False,
                framework=framework_name,
                message=f"Uninstall failed: {str(e)}"
            )
    
    async def install_all(
        self, 
        on_progress: Optional[Callable[[str, str, float], None]] = None
    ) -> Dict[str, InstallResult]:
        """Install all frameworks with dependency ordering
        
        Args:
            on_progress: Callback(framework_name, message, progress_percent)
        """
        results = {}
        # Installation order matters: RED4ext must be first
        install_order = ['red4ext', 'tweakxl', 'archivexl']
        total = len(install_order)
        
        for i, name in enumerate(install_order):
            if on_progress:
                on_progress(name, f"Installing {name}...", (i / total) * 100)
            
            results[name] = await self.install(name)
            
            if on_progress:
                progress = ((i + 1) / total) * 100
                if results[name].success:
                    on_progress(name, f"{name} installed successfully", progress)
                else:
                    on_progress(name, f"{name} installation failed: {results[name].message}", progress)
        
        return results
    
    async def install_selected(
        self,
        frameworks: List[str],
        on_progress: Optional[Callable[[str, str, float], None]] = None
    ) -> Dict[str, InstallResult]:
        """Install selected frameworks with dependency ordering
        
        Args:
            frameworks: List of framework names to install
            on_progress: Callback(framework_name, message, progress_percent)
        """
        results = {}
        
        # Ensure proper installation order
        install_order = []
        if 'red4ext' in frameworks:
            install_order.append('red4ext')
        if 'tweakxl' in frameworks:
            # TweakXL requires RED4ext
            if 'red4ext' not in install_order:
                install_order.insert(0, 'red4ext')
            install_order.append('tweakxl')
        if 'archivexl' in frameworks:
            # ArchiveXL requires RED4ext
            if 'red4ext' not in install_order:
                install_order.insert(0, 'red4ext')
            install_order.append('archivexl')
        
        total = len(install_order)
        
        for i, name in enumerate(install_order):
            if on_progress:
                on_progress(name, f"Installing {name}...", (i / total) * 100)
            
            results[name] = await self.install(name)
            
            if on_progress:
                progress = ((i + 1) / total) * 100
                if results[name].success:
                    on_progress(name, f"{name} installed successfully", progress)
                else:
                    on_progress(name, f"{name} failed: {results[name].message}", progress)
                    # Don't continue if RED4ext fails (dependency)
                    if name == 'red4ext' and not results[name].success:
                        break
        
        return results
    
    async def update_all(self) -> Dict[str, InstallResult]:
        """Update all installed frameworks"""
        results = {}
        for name in self.FRAMEWORKS:
            status = await self.check_status(name)
            if status.installed:
                results[name] = await self.update(name)
        return results


class LogWatcher:
    """Watches RED4ext and game logs in real-time"""
    
    def __init__(self, game_path: Path):
        self.game_path = game_path
        self.log_paths = [
            game_path / "red4ext" / "logs" / "red4ext.log",
            game_path / "red4ext" / "logs" / "plugins.log",
        ]
    
    async def get_recent_logs(self, lines: int = 100) -> List[str]:
        """Get recent log lines"""
        all_lines = []
        
        for log_path in self.log_paths:
            if log_path.exists():
                try:
                    async with aiofiles.open(log_path, 'r') as f:
                        content = await f.read()
                        all_lines.extend(content.splitlines()[-lines:])
                except Exception:
                    pass
        
        return all_lines
    
    async def get_errors(self) -> List[str]:
        """Get error lines from logs"""
        errors = []
        
        for log_path in self.log_paths:
            if log_path.exists():
                try:
                    async with aiofiles.open(log_path, 'r') as f:
                        async for line in f:
                            if '[ERROR]' in line or '[WARN]' in line:
                                errors.append(line.strip())
                except Exception:
                    pass
        
        return errors
    
    async def watch(self):
        """Generator that yields new log lines as they appear"""
        positions = {}
        
        for log_path in self.log_paths:
            if log_path.exists():
                positions[log_path] = log_path.stat().st_size
        
        while True:
            for log_path in self.log_paths:
                if log_path.exists():
                    current_size = log_path.stat().st_size
                    last_pos = positions.get(log_path, 0)
                    
                    if current_size > last_pos:
                        async with aiofiles.open(log_path, 'r') as f:
                            await f.seek(last_pos)
                            new_content = await f.read()
                            positions[log_path] = current_size
                            
                            for line in new_content.splitlines():
                                yield line
            
            await asyncio.sleep(0.5)


class GameProcessMonitor:
    """Monitors the Cyberpunk 2077 game process"""
    
    def __init__(self, game_path: Path):
        self.game_path = game_path
        self.process_name = "Cyberpunk2077"
    
    async def is_running(self) -> bool:
        """Check if game is running"""
        import subprocess
        try:
            result = subprocess.run(
                ['pgrep', '-f', self.process_name],
                capture_output=True, text=True
            )
            return result.returncode == 0
        except Exception:
            return False
    
    async def get_pid(self) -> Optional[int]:
        """Get game process ID"""
        import subprocess
        try:
            result = subprocess.run(
                ['pgrep', '-f', self.process_name],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                return int(result.stdout.strip().split('\n')[0])
        except Exception:
            pass
        return None
    
    async def get_memory_usage(self) -> Optional[int]:
        """Get game memory usage in bytes"""
        pid = await self.get_pid()
        if not pid:
            return None
        
        import subprocess
        try:
            result = subprocess.run(
                ['ps', '-p', str(pid), '-o', 'rss='],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                # rss is in KB
                return int(result.stdout.strip()) * 1024
        except Exception:
            pass
        return None
    
    async def get_uptime(self) -> Optional[float]:
        """Get game uptime in seconds"""
        pid = await self.get_pid()
        if not pid:
            return None
        
        import subprocess
        try:
            result = subprocess.run(
                ['ps', '-p', str(pid), '-o', 'etime='],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                etime = result.stdout.strip()
                # Parse elapsed time (format: [[dd-]hh:]mm:ss)
                parts = etime.replace('-', ':').split(':')
                parts = [int(p) for p in parts]
                
                if len(parts) == 2:
                    return parts[0] * 60 + parts[1]
                elif len(parts) == 3:
                    return parts[0] * 3600 + parts[1] * 60 + parts[2]
                elif len(parts) == 4:
                    return parts[0] * 86400 + parts[1] * 3600 + parts[2] * 60 + parts[3]
        except Exception:
            pass
        return None
