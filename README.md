# Library Management System

A comprehensive desktop application for managing campus library operations, including book catalog management, user administration, circulation tracking, and detailed reporting. Built with Python and PyQt6 for a native desktop experience.

## Features

### 📚 **Book Catalog Management**
- Add, view, edit, and delete books from the library collection
- Track total copies and available copies for each book
- ISBN and unique book ID tracking
- Publisher and author information management
- Search and filter books by various criteria

### 👥 **User Management**
- Register and manage library users (Students, Faculty, Librarians, Admins)
- Support for multiple departments (CSE, ECE, EEE, CE, ME, AU, PH, EV, ET)
- Contact information and user role management
- View user borrowing history and book status
- Delete users with proper validation

### 📤 **Book Circulation**
- Issue books to users with customizable loan periods
- Track book checkout and return dates
- Automatic fine calculation for overdue books
- One-click book returns with fine notification
- Real-time inventory management
- Comprehensive circulation logs

### 📊 **Dashboard & Reports**
- Real-time library statistics
- Total students and books tracking
- Daily issued and returned books count
- Overdue books monitoring
- Available books inventory display
- Unpaid fines tracking
- Circulation history reports

### 🔐 **Settings & Security**
- Admin password protection
- Configurable daily fine rates
- Default loan period customization
- Settings persistence

### 📱 **Barcode Support**
- **Barcode Generation**: Generate Code128 barcodes for books with preview
- **Quick Scan**: Real-time barcode scanning with camera integration
- **Dual Input**: Support for hardware USB scanners and manual entry
- **PNG Export**: Save generated barcodes for printing

## Technical Stack

- **Language**: Python 3.x
- **GUI Framework**: PyQt6
- **Database**: SQLite3
- **Barcode Processing**: python-barcode, Pillow, cv2
- **Scanning**: OpenCV (cv2)

## Project Structure

```
campus-library/
├── main.py                    # Application entry point
├── mainwindow.py             # Main window layout and navigation
├── database.py               # SQLite database operations
├── email_queue.py            # Offline email queue and background SMTP sync
├── email_service.py          # SMTP delivery and notification payloads
├── dialogs.py                # Dialog windows for various operations
├── utils.py                  # Utility functions
├── pages/
│   ├── dashboard_view.py     # Dashboard with library statistics
│   ├── bookcatalog_view.py   # Book management interface
│   ├── usermanagement_view.py # User management interface
│   ├── circulation_view.py    # Book circulation interface
│   ├── reports_view.py        # Reports and analytics
│   └── settings_view.py       # System settings
├── assets/
│   ├── library_icon.ico       # Application icon
│   └── library_icon.png       # Splash screen image
└── README.md                  # This file
```

## Installation & Setup

### Requirements
- Python 3.7+
- pip (Python package manager)

### Dependencies Installation

Install required packages:

```bash
pip install PyQt6 pillow opencv-python python-barcode openpyxl
```

### Running the Application

1. Navigate to the project directory:
```bash
cd campus-library
```

2. Run the application:
```bash
python main.py
```

3. Enter the default admin password: **`admin123`** on a new database.
4. On first sign-in, save the administrator recovery code somewhere safe.
   The code is shown once and is required to reset a forgotten password.

Use **Forgot password?** on the login screen and enter the saved recovery
code to choose a new password. A successful reset replaces the recovery code;
save the newly displayed code before continuing. You can also replace the
recovery code from **Settings → Administrator Security** while signed in.

The password and recovery code are stored as salted hashes in the local
database. Existing databases migrate the legacy password after a successful
sign-in. For security, an older database with a forgotten password and no
previously saved recovery code cannot be reset locally; there is no safe way
for an offline EXE to verify ownership otherwise.

## Email Notifications, Complaints, and Online Backups

Optional email and Google Drive integrations require the service dependencies:

```bash
pip install -r requirements-services.txt
```

In **Settings → Email Notifications**, enter the Gmail sender and library
contact address. Use a Gmail **App Password** (with 2-Step Verification
enabled), not the account password; enter it in the app and save it. The
password is stored in the signed-in Windows account's Credential Manager,
not in the database. Enable due-date reminders to send one email on a loan's
due date and one when it becomes overdue. Student email addresses can be
entered in User Management or included in user CSV/XLSX imports.
Registration, issue, return, reminder, and system-alert messages are first
written to the local SQLite email queue. The background sync checks for
connectivity at startup and every minute, but queued delivery is disabled by
default. In **Settings**, enable it only after verifying the saved recipient
addresses; enabling requires confirmation. When delivery is disabled, queued
messages remain stored locally and are not sent. Use **Manage Queue** to review
message recipients and content, filter by status, delete selected messages
(including sent history), or clear all pending and failed messages. Deleting
messages requires delivery to be disabled. **Sync Now** retries queued or
previously failed messages only when delivery is enabled. SMTP
delivery runs on a worker thread, and temporary delivery failures retry with
backoff before being marked failed. The header and Settings page show the
queue state.

The librarian can submit and track user complaints in User Management.
Complaints are saved locally and notifications are added to the email queue
for the configured library contact and, when available, the student. This is
an in-app librarian workflow, not a public student portal.

In **Settings → Encrypted Google Drive Backup**, connect with a Google OAuth
**Desktop app** client JSON file from a Google Cloud project where the Drive
API is enabled. The app uploads AES-GCM encrypted database copies. The OAuth
token and backup key are stored in the signed-in Windows account's Credential
Manager. Export the backup recovery key and keep it securely outside the
computer; without it, backups cannot be recovered if that Windows profile is
lost. Restore writes to a separate database file and does not overwrite the
currently open database.

Automatic daily uploads are optional and run while the application is open,
after a successful Drive connection and when enabled in backup settings.
Without saved Drive authorization, no automatic upload is attempted. Email
messages created while offline remain queued locally until connectivity is
available; Google Drive backups still require an internet connection.

## Building a Windows EXE and Installer (PyInstaller + Inno Setup)

This project can be packaged into a standalone Windows executable using PyInstaller and distributed with an installer created by Inno Setup. Below are step-by-step instructions using a provided `main.spec` and an Inno Setup `.iss` file.

Prerequisites
- Windows machine (for Inno Setup compilation)
- Python 3.x and required packages installed in your environment
- PyInstaller (pip install pyinstaller)
- Inno Setup (https://jrsoftware.org/) — install Inno Setup Compiler (ISCC.exe)
- Optional: code signing tools (signtool) if you need signed binaries

1) Create the executable with PyInstaller

- If you already have a `main.spec` in the repo (customized to include data files and icon), use it directly:

```bash
# From the project root
pyinstaller main.spec
```

- If you need to generate a `.spec` automatically, you can run a PyInstaller command and then tweak the generated spec:

```bash
# One-file, windowed (no console), with icon and assets folder included
pyinstaller --name "LibCore" --onefile --windowed --icon=assets/library_icon.ico \
  --add-data "assets;assets" main.py
```

Notes about the spec file (main.spec)
- A spec file controls how PyInstaller bundles your app (one-file vs one-folder, data files, binaries, hiddenimports, etc.).
- If your app uses dynamic imports or Qt plugins, ensure `hiddenimports` and `datas` include those files.
- Example minimal adjustments you may need in main.spec:

```python
# main.spec (snippet)
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis([
    'main.py',
],
    pathex=['.'],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz,
    a.scripts,
    exclude_binaries=True,
    name='LibCore',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='assets/library_icon.ico',
)

coll = COLLECT( ... )  # for one-folder builds
```

- After running `pyinstaller main.spec`, look in the `dist/` directory. For a one-file build you'll have `dist/LibCore.exe`. For a one-folder build you'll have `dist/LibCore/` containing the executable and supporting files.

2) Create an Inno Setup installer (.iss)

- Create an installer script (e.g., `installer.iss`) that references the produced EXE (or the one-folder `dist` directory).
- Example `.iss` for a one-file EXE:

```ini
; installer.iss
[Setup]
AppName=LibCore - Campus Library
AppVersion=1.0
DefaultDirName={pf}\LibCore
DefaultGroupName=LibCore
OutputBaseFilename=LibCore_Installer
Compression=lzma
SolidCompression=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; For one-file build
Source: "dist\LibCore.exe"; DestDir: "{app}"; Flags: ignoreversion
; If you have additional files (README, LICENSE), add them too:
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\LibCore"; Filename: "{app}\LibCore.exe"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\LibCore.exe"; Description: "Launch LibCore"; Flags: nowait postinstall skipifsilent
```

- Example `.iss` adjustments for a one-folder build (use Source: "dist\LibCore\*"; Flags: recursesubdirs createallsubdirs)

```ini
[Files]
Source: "dist\LibCore\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
```

3) Compile the Inno Setup script

- Open `installer.iss` in Inno Setup Compiler and press Compile, or use the command-line compiler:

```powershell
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" path\to\installer.iss
```

- The resulting installer (e.g., `LibCore_Installer.exe`) will be created in the same folder as the .iss or the configured OutputDir.

4) Test the installer

- Run the generated installer on a clean Windows VM or test machine.
- Verify installation path, shortcuts, application launch, and that all assets (icons, images, config files) are present and working.

5) Notes and Troubleshooting

- PyInstaller and Qt: PyQt6 apps sometimes require adding Qt plugins (platforms, imageformats). If the app fails to start, check the PyInstaller warnings and ensure Qt plugins are bundled (use `--add-data` or add to `datas` in the spec).
- Data files path: When bundling with one-file, files are extracted to a temporary folder at runtime; use runtime-safe file access (e.g., use sys._MEIPASS to locate bundled data when frozen).

Example helper in Python to load bundled asset paths:

```python
import sys
import os

def resource_path(relative_path):
    # Get absolute path to resource, works for dev and for PyInstaller bundle
    base_path = getattr(sys, '_MEIPASS', os.path.abspath('.'))
    return os.path.join(base_path, relative_path)

# Usage: icon_path = resource_path('assets/library_icon.ico')
```

- If your build uses native extensions (cv2) ensure the correct DLLs are included; check the `binaries` section in the spec.

- Code signing: For distribution, consider signing the executable and installer using signtool (Windows) to avoid SmartScreen warnings.

6) Cleanup

Use these commands to clean PyInstaller build artifacts before rebuilding:

```bash
rm -rf build dist __pycache__
# On Windows PowerShell:
Remove-Item -Recurse -Force build,dist,__pycache__
```

## In-app Windows Updates

The packaged Windows application includes **Settings → Application Updates**.
Select **Check for Updates** to query the latest stable GitHub Release. If a
newer release is available, confirm the update; the app downloads and validates
`Library-Windows.zip` against GitHub's SHA-256 asset digest, closes, replaces
its installed application folder, and restarts. The library database is stored
outside that folder and is not part of the update package.
If replacement fails, the helper restores and relaunches the prior build; its
diagnostic log is `%TEMP%\LibraryUpdate.log`.

To publish a Windows update:

1. Set the same new numeric version in `app_version.py` and
   `installer_scipt.iss` (for example, `2.1`), then build the application:

   ```powershell
   pyinstaller --noconfirm --clean main.spec
   ```

2. Create the updater package from the *contents* of `dist\main` so that
   `Library.exe` is at the ZIP root:

   ```powershell
   Compress-Archive -Path .\dist\main\* `
     -DestinationPath .\Library-Windows.zip -Force
   ```

3. On GitHub, open the repository's **Releases** page, select **Draft a new
   release**, create a new tag such as `v2.1` targeting `main`, enter release
   notes, and upload `Library-Windows.zip`.
4. Publish the release as a normal/latest release, not a draft or pre-release.
   The updater checks only the latest published stable release. Wait until the
   uploaded asset is listed with a SHA-256 digest in the release API before
   testing.
5. Test from an installed older version (for example, v2.0): open **Settings →
   Application Updates → Check for Updates**, confirm v2.1, and verify that
   the application restarts with the new version. Keep the v2.0 installation
   until the update and restart are confirmed.

The in-app updater requires the exact asset name `Library-Windows.zip`, a
numeric version tag newer than the installed version, and a ZIP whose root
contains the full contents of `dist\main`, including `Library.exe`. The
installer defaults to the current user's writable
`%LOCALAPPDATA%\Programs\Library` folder so self-update can replace its files.
If an older installation is under `Program Files`, install that version in the
user folder before testing self-update. Source-code runs and non-Windows builds
can check for updates but cannot replace themselves.
The installed app displays its version in both the title bar and header badge.
When the updater installs a release, it records the release tag alongside the
application so those labels and future update checks use the installed version.
For a new installer or manually downloaded ZIP, still update `app_version.py`
to the release version before building.
Administrators can use **Settings → Application Updates → Manage Versions** to
review published stable releases and install a verified release, including an
older release as a rollback. Each release must include `Library-Windows.zip`
with a GitHub SHA-256 digest. Version management requires the administrator
password; installing or rolling back is available only in the packaged
Windows application. The installed version is recorded with the application
files and shown in the title bar and header badge.
Until the first stable release is published, GitHub's `/releases/latest`
endpoint returns 404; the app reports that no release is available and links
to the Releases page. Publish a stable release with the package above before
expecting an update to be found.

## Default Configuration

| Setting | Default Value |
|---------|---------------|
| Initial Admin Password | `admin123` (new databases only) |
| Daily Fine Rate | 10.00 (currency units) |
| Default Loan Period | 14 days |

## Usage Guide

### 📖 Dashboard
- View real-time library statistics
- Monitor daily issued/returned books
- Check overdue books and unpaid fines
- See available books inventory

### 📚 Books Details
- **Add Book**: Click "New Book" to add books to catalog
- **Edit**: Select a book and click "Edit" to modify details
- **Delete**: Remove books (only if no copies are currently checked out)
- **Import CSV/XLSX**: Include `book_id`, `title`, and `publisher`; book IDs must be exactly 5 digits and title/publisher are required
- **Generate Barcode**: Create and print barcodes for books
- **Batch Circulation**: Select multiple books, then use the Actions tab to issue or return them for one user

### 👤 Users Details
- **Add User**: Register new library users with department and role
- **Edit User**: Update user information
- **Import CSV/XLSX**: Student IDs use `24001-CS-097` format (5 digits, a 2-letter branch code, then 3 digits); employee IDs use 6 digits (for example, `123456`). Phone numbers, when provided, must contain exactly 10 digits. Students need a college branch; faculty and guest lecturers need a college branch, Sciences & Humanities Department, or General Administration.
- **Delete**: Remove users without active checkouts
- **View Books**: See all books borrowed by a user
- **Batch Circulation**: Select multiple users, then use Actions to issue or return one book for each selected user
- **Send Email**: Select one user, open Actions, and compose an email; it is queued for delivery when email sync is available

### 📤 Circulation
- **Issue Book**: Check out books to users using barcode scan or ID entry
- **Return Book**: Process book returns with automatic fine calculation
- **Quick Scan**: Use camera or hardware scanner for faster operations
- **Set Loan Period**: Customize days allowed for each transaction

### 📊 Reports
- View circulation logs with detailed transaction history
- Track checkout dates, due dates, and return dates
- Monitor fine amounts and payment status
- Export and analyze library usage patterns

### ⚙️ Settings
- Update admin password
- Configure daily fine rate
- Set default loan period

## Database Schema

### Users Table
- `id` (PRIMARY KEY): Unique user identifier
- `phone_number` (UNIQUE): Contact number
- `full_name`: User's full name
- `role`: Student/Faculty/Librarian/Admin
- `department`: Department affiliation
- `created_at`: Registration timestamp

### Books Table
- `id` (PRIMARY KEY): Unique book identifier
- `isbn` (UNIQUE): ISBN number
- `title`: Book title
- `author`: Author name
- `publisher`: Publisher name
- `total_copies`: Total copies in library
- `available_copies`: Currently available copies
- `created_at`: Addition timestamp

### Circulation Logs Table
- `id` (PRIMARY KEY): Log entry ID
- `book_id`: Reference to books table
- `user_id`: Reference to users table
- `checkout_date`: Issue date and time
- `due_date`: Expected return date
- `return_date`: Actual return date
- `fine_amount`: Overdue fine charged
- `status`: ISSUED/RETURNED

### Settings Table
- `key` (PRIMARY KEY): Setting name
- `value`: Setting value

## Error Handling

The application includes comprehensive error handling with user-friendly messages for:
- Duplicate book/user entries
- Foreign key constraint violations
- Database integrity issues
- File operations
- Scanner/camera connectivity problems

## Features Details

### Barcode Generation
- Supports Code128 barcode format
- Configurable module width and height for scanner compatibility
- Real-time preview before saving
- High-quality PNG export for printing

### Circulation Logic
- Prevents duplicate checkouts
- Validates user and book existence
- Calculates fines based on configurable daily rates
- Handles cascading deletes for data integrity
- Manages inventory automatically

### Security
- Password-protected admin access
- Database-level constraints
- Transaction management with rollback on errors

## Troubleshooting

### Camera Not Working in Quick Scan
- Ensure camera is connected and recognized by the system
- Check application permissions for camera access
- Try closing and reopening the dialog

### Barcode Scanner Not Detected
- Verify USB scanner driver installation
- Ensure scanner is configured for HID (Human Interface Device) mode
- The application accepts both camera and hardware scanner input

### Database Errors
- Restart the application to reset database connection
- Check disk space for database file storage
- Verify write permissions in appdata directory

## Future Enhancements

- Multi-branch library support
- Advanced reporting and analytics
- Mobile application for student access
- Email notifications for due dates
- Reservation system
- eBook integration

## License

This project is developed for campus library management purposes.

## Support

For issues or questions about the application, please check the troubleshooting section or contact the development team.

---

**LibCore v1.0** - Streamlining Campus Library Operations
