# LibCore - Campus Library Management System

A comprehensive desktop application for managing campus library operations, including book catalog management, user administration, circulation tracking, and detailed reporting. Built with Python and PyQt6 with SQLite database backend.

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
pip install PyQt6 pillow opencv-python python-barcode
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

3. Enter the default admin password: **`admin123`**

## Default Configuration

| Setting | Default Value |
|---------|---------------|
| Admin Password | `admin123` |
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
- **Generate Barcode**: Create and print barcodes for books

### 👤 Users Details
- **Add User**: Register new library users with department and role
- **Edit User**: Update user information
- **Delete**: Remove users without active checkouts
- **View Books**: See all books borrowed by a user

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
