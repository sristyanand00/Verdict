#!/usr/bin/env python3
"""
Create a cross-platform compatible ZIP for BIRD dataset
Fixes the backslash issue for Kaggle upload
"""

import zipfile
import os
from pathlib import Path

def create_bird_zip():
    source_dir = Path(r"c:\Users\Dell\OneDrive\Desktop\verdict\datasets")
    zip_path = Path(r"c:\Users\Dell\OneDrive\Desktop\verdict\BIRD_dataset.zip")
    
    # Remove old ZIP if exists
    if zip_path.exists():
        zip_path.unlink()
        print(f"Removed old ZIP file")
    
    print("Creating cross-platform ZIP file...")
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add root files
        root_files = ["dev.json", "dev.sql", "dev_tables.json", "dev_tied_append.json"]
        for filename in root_files:
            file_path = source_dir / filename
            if file_path.exists():
                # Use forward slashes in ZIP
                arcname = filename
                print(f"Adding: {arcname}")
                zf.write(file_path, arcname=arcname)
        
        # Add dev_databases directory
        dev_databases = source_dir / "dev_databases"
        if dev_databases.exists():
            count = 0
            for file_path in dev_databases.rglob("*"):
                if file_path.is_file():
                    # Get relative path and ensure forward slashes
                    relative_path = file_path.relative_to(source_dir)
                    # Convert to forward slashes (POSIX style) for cross-platform compatibility
                    arcname = relative_path.as_posix()
                    
                    zf.write(file_path, arcname=arcname)
                    count += 1
                    if count % 50 == 0:
                        print(f"Added {count} files...")
            
            print(f"Total files added from dev_databases: {count}")
    
    # Verify the ZIP
    print("\nVerifying ZIP...")
    with zipfile.ZipFile(zip_path, 'r') as zf:
        entries = zf.namelist()
        total = len(entries)
        
        # Check for backslashes
        bad_paths = [e for e in entries if '\\' in e]
        
        print(f"\nTotal entries: {total}")
        print(f"\nFirst 15 entries:")
        for entry in entries[:15]:
            print(f"  {entry}")
        
        if bad_paths:
            print(f"\nWARNING: Found {len(bad_paths)} entries with backslashes!")
            for path in bad_paths[:5]:
                print(f"  {path}")
        else:
            print(f"\nSUCCESS: All {total} entries use forward slashes!")
            print("This ZIP is ready for Kaggle upload!")
    
    # Show file size
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"\nZIP file created: {size_mb:.2f} MB")
    print(f"Location: {zip_path}")

if __name__ == "__main__":
    create_bird_zip()
