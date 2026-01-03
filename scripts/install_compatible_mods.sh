#!/bin/bash
#
# Cyberpunk 2077 macOS Mod Installer Script
# Installs compatible mods with backup and rollback support
#
# Usage:
#   ./install_compatible_mods.sh              # Interactive mode
#   ./install_compatible_mods.sh --yes        # Auto-confirm all
#   ./install_compatible_mods.sh --dry-run    # Show what would be installed
#   ./install_compatible_mods.sh --rollback   # Restore from last backup
#

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="/tmp/mod_install_$(date +%Y%m%d_%H%M%S).log"
BACKUP_ID_FILE="/tmp/last_mod_backup_id.txt"
INSTALLED_MODS_FILE="/tmp/installed_mods_session.txt"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
DRY_RUN=false
AUTO_CONFIRM=false
ROLLBACK=false
CATEGORY=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --yes|-y)
            AUTO_CONFIRM=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --rollback)
            ROLLBACK=true
            shift
            ;;
        --category)
            CATEGORY="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --yes, -y       Auto-confirm all prompts"
            echo "  --dry-run       Show what would be installed without installing"
            echo "  --rollback      Restore from last backup"
            echo "  --category CAT  Install only specific category (texture, redscript, archivexl)"
            echo "  --help, -h      Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Mod definitions - grouped by category and priority
# Format: MOD_ID|NAME|CATEGORY|PRIORITY|DEPENDENCIES
declare -a MODS=(
    # HD/Texture Mods (safe, no dependencies)
    "7652|Cyberpunk 2077 HD Reworked Project|texture|1|"
    "8157|Preem Skin|texture|1|"
    "8275|Preem Water 2.0|texture|1|"
    "17811|Realistic Map|texture|1|"
    "7160|Better Building Windows|texture|1|"
    "8105|Blur Begone|texture|1|"
    "3901|Enhanced Weather V6|texture|1|"
    "3040|2077 More Gore V3.0|texture|1|"
    "3196|Weather Probability Rebalance|texture|1|"
    
    # Redscript Mods (require Redscript framework)
    "3858|Ragdoll Physics Overhaul|redscript|2|"
    "1654|Kiroshi Opticals - Crowd Scanner|redscript|2|"
    "1512|Annoy Me No More|redscript|2|"
    "2687|Smarter Scrapper|redscript|2|"
    "5115|Immersive Timeskip|redscript|2|"
    "3963|No Special Outfit Lock|redscript|2|"
    "9496|Enable Finisher Ragdolls|redscript|2|"
    "5534|Talk to Me|redscript|2|"
    
    # ArchiveXL Mods (require ArchiveXL framework)
    "12681|H10 Megabuilding Unlocked|archivexl|3|"
    "5437|V's Edgerunners Mansion|archivexl|3|"
    "2592|Limited HUD|archivexl|3|"
    
    # TweakXL Mods (require TweakXL framework)
    "15043|New Game Plus - Native|tweakxl|3|"
    "18318|Deceptious Bug Fixes|tweakxl|3|"
)

log() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

log_success() {
    log "${GREEN}✓${NC} $1"
}

log_error() {
    log "${RED}✗${NC} $1"
}

log_warn() {
    log "${YELLOW}⚠${NC} $1"
}

log_info() {
    log "${BLUE}ℹ${NC} $1"
}

# Function to run mod-manager command
run_mod_manager() {
    cd "$PROJECT_DIR"
    python -m app.tui.cli "$@" 2>&1
}

# Rollback function
do_rollback() {
    log_info "Starting rollback..."
    
    if [[ ! -f "$BACKUP_ID_FILE" ]]; then
        log_error "No backup ID found. Cannot rollback."
        exit 1
    fi
    
    BACKUP_ID=$(cat "$BACKUP_ID_FILE")
    log_info "Restoring backup: $BACKUP_ID"
    
    if $AUTO_CONFIRM; then
        run_mod_manager backup restore "$BACKUP_ID" --yes
    else
        run_mod_manager backup restore "$BACKUP_ID"
    fi
    
    if [[ $? -eq 0 ]]; then
        log_success "Rollback completed successfully!"
        
        # Uninstall mods installed in this session
        if [[ -f "$INSTALLED_MODS_FILE" ]]; then
            log_info "Uninstalling mods from this session..."
            while read -r mod_id; do
                log_info "Uninstalling mod ID: $mod_id"
                run_mod_manager uninstall "$mod_id" --yes 2>/dev/null || true
            done < "$INSTALLED_MODS_FILE"
            rm -f "$INSTALLED_MODS_FILE"
        fi
    else
        log_error "Rollback failed!"
        exit 1
    fi
}

# Handle rollback request
if $ROLLBACK; then
    do_rollback
    exit 0
fi

# Main installation flow
main() {
    log ""
    log "╔════════════════════════════════════════════════════════════════╗"
    log "║     Cyberpunk 2077 macOS Compatible Mod Installer             ║"
    log "╚════════════════════════════════════════════════════════════════╝"
    log ""
    log "Log file: $LOG_FILE"
    log ""
    
    # Filter mods by category if specified
    declare -a FILTERED_MODS=()
    for mod in "${MODS[@]}"; do
        IFS='|' read -r mod_id name category priority deps <<< "$mod"
        if [[ -z "$CATEGORY" ]] || [[ "$category" == "$CATEGORY" ]]; then
            FILTERED_MODS+=("$mod")
        fi
    done
    
    # Count mods by category
    local texture_count=0
    local redscript_count=0
    local archivexl_count=0
    local tweakxl_count=0
    
    for mod in "${FILTERED_MODS[@]}"; do
        IFS='|' read -r mod_id name category priority deps <<< "$mod"
        case $category in
            texture) ((texture_count++)) ;;
            redscript) ((redscript_count++)) ;;
            archivexl) ((archivexl_count++)) ;;
            tweakxl) ((tweakxl_count++)) ;;
        esac
    done
    
    log "Mods to install:"
    log "  🎨 Texture/HD mods:  $texture_count"
    log "  📜 Redscript mods:   $redscript_count"
    log "  📦 ArchiveXL mods:   $archivexl_count"
    log "  🔧 TweakXL mods:     $tweakxl_count"
    log "  ─────────────────────"
    log "  Total:               ${#FILTERED_MODS[@]}"
    log ""
    
    if $DRY_RUN; then
        log_warn "DRY RUN MODE - No changes will be made"
        log ""
        log "Would install the following mods:"
        log ""
        for mod in "${FILTERED_MODS[@]}"; do
            IFS='|' read -r mod_id name category priority deps <<< "$mod"
            log "  [$mod_id] $name ($category)"
        done
        exit 0
    fi
    
    # Confirmation
    if ! $AUTO_CONFIRM; then
        read -p "Continue with installation? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Installation cancelled."
            exit 0
        fi
    fi
    
    # Create backup
    log ""
    log_info "Creating pre-installation backup..."
    BACKUP_OUTPUT=$(run_mod_manager backup create --name "pre-mod-install-$(date +%Y%m%d_%H%M%S)")
    
    if [[ $? -eq 0 ]]; then
        # Extract backup ID from output
        BACKUP_ID=$(echo "$BACKUP_OUTPUT" | grep -oE 'Backup created: [^ ]+' | cut -d' ' -f3 || echo "unknown")
        echo "$BACKUP_ID" > "$BACKUP_ID_FILE"
        log_success "Backup created: $BACKUP_ID"
        log_info "To rollback: $0 --rollback"
    else
        log_warn "Backup creation failed (continuing anyway)"
    fi
    
    # Clear installed mods tracking
    > "$INSTALLED_MODS_FILE"
    
    # Install mods by priority (lower = install first)
    local success_count=0
    local fail_count=0
    local skip_count=0
    
    log ""
    log "Starting installation..."
    log ""
    
    # Sort by priority and install
    for priority in 1 2 3; do
        for mod in "${FILTERED_MODS[@]}"; do
            IFS='|' read -r mod_id name category mod_priority deps <<< "$mod"
            
            if [[ "$mod_priority" != "$priority" ]]; then
                continue
            fi
            
            log "────────────────────────────────────────────────────────"
            log_info "[$mod_id] $name"
            log "        Category: $category | Priority: $priority"
            
            # Check if already installed
            EXISTING=$(run_mod_manager list 2>/dev/null | grep -E "^\s*$mod_id\s+" || true)
            if [[ -n "$EXISTING" ]]; then
                log_warn "Already installed, skipping"
                ((skip_count++))
                continue
            fi
            
            # Install the mod
            log "        Installing from Nexus..."
            
            INSTALL_OUTPUT=$(run_mod_manager install "nexus:$mod_id" --yes --skip-compatibility 2>&1)
            INSTALL_EXIT=$?
            
            if [[ $INSTALL_EXIT -eq 0 ]]; then
                log_success "Installed successfully"
                echo "$mod_id" >> "$INSTALLED_MODS_FILE"
                ((success_count++))
            else
                # Check for premium requirement
                if echo "$INSTALL_OUTPUT" | grep -q "Premium\|403"; then
                    log_warn "Nexus Premium required - download manually:"
                    log "        https://www.nexusmods.com/cyberpunk2077/mods/$mod_id"
                    ((skip_count++))
                else
                    log_error "Installation failed: $(echo "$INSTALL_OUTPUT" | tail -1)"
                    ((fail_count++))
                    
                    # Ask to continue or abort
                    if ! $AUTO_CONFIRM; then
                        read -p "Continue with remaining mods? (Y/n) " -n 1 -r
                        echo
                        if [[ $REPLY =~ ^[Nn]$ ]]; then
                            log_warn "Installation aborted by user"
                            log_info "To rollback: $0 --rollback"
                            break 2
                        fi
                    fi
                fi
            fi
            
            # Small delay to avoid rate limiting
            sleep 1
        done
    done
    
    # Summary
    log ""
    log "╔════════════════════════════════════════════════════════════════╗"
    log "║                    INSTALLATION SUMMARY                        ║"
    log "╚════════════════════════════════════════════════════════════════╝"
    log ""
    log "  ${GREEN}✓ Successful:${NC}  $success_count"
    log "  ${RED}✗ Failed:${NC}      $fail_count"
    log "  ${YELLOW}⊘ Skipped:${NC}     $skip_count"
    log ""
    log "  Log file:     $LOG_FILE"
    log "  Backup ID:    $(cat "$BACKUP_ID_FILE" 2>/dev/null || echo 'none')"
    log ""
    
    if [[ $fail_count -gt 0 ]]; then
        log_warn "Some installations failed."
        log_info "To rollback all changes: $0 --rollback"
    else
        log_success "Installation complete!"
    fi
    
    # List installed mods
    log ""
    log "Currently installed mods:"
    run_mod_manager list
}

# Run main
main
