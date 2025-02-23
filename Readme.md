# Inventory Manager

Inventory Manager is a Django-based web application that helps users manage and track their inventory effectively. It provides authentication features, including user sign-up, sign-in, and logout, along with a user-friendly interface for managing inventory data.

## Features

- **User Authentication**: 
  - Sign up for new users.
  - Sign in for existing users.
  - Secure logout functionality using Django's built-in `LogoutView`.

- **Inventory Management**:
  - Add, update, and delete inventory items.
  - View and search inventory records.

- **Responsive Design**:
  - Mobile-friendly navigation bar and interface.
  - Clean and intuitive UI for easy navigation.

## Technologies Used

- **Frontend**: HTML, CSS, Bootstrap
- **Backend**: Django Framework
- **Database**: SQLite (default Django database; replaceable with other options like PostgreSQL or MySQL)

## Getting Started

### Prerequisites
- Python 3.8+
- Django 4.0+
- A code editor (e.g., VS Code, PyCharm)
- Git (for version control)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/inventory-manager.git
   cd inventory-manager
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install django
   pip install crispy-forms
   pip install crispy-bootstrap5
   or pip install -r requirements.txt
   ```

4. Apply database migrations:
   ```bash
   python manage.py migrate
   ```

5. Run the development server:
   ```bash
   python manage.py runserver
   ```

6. Open your browser and visit: `http://127.0.0.1:8000/` or hold Ctrl + click on the link in the terminal when you run the server

## Usage

1. **Sign Up**: Create a new account by visiting the Sign Up page.
2. **Sign In**: Log in using your registered credentials.
3. **Manage Inventory**:
   - Use the dashboard to add, update, or delete inventory items.
4. **Logout**: Click the "Sign Out" button to securely log out.

## Troubleshooting

If you encounter a "405 Method Not Allowed" error during logout:
- Ensure your logout button sends a POST request (recommended).
- Alternatively, customize the logout view to accept GET requests.

Refer to the [Django documentation](https://docs.djangoproject.com/en/stable/ref/contrib/auth/) for more details on authentication views.

## Contributing

Contributions are welcome! If you'd like to contribute:
1. Fork the repository.
2. Create a new branch for your feature or fix.
3. Submit a pull request with a detailed explanation of your changes.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## Acknowledgements

- Django Framework
- Bootstrap CSS

---

## Requirements
django>=4.0,<5.0
crispy-forms>=1.14.0,<2.0
crispy-bootstrap5>=0.7


Feel free to reach out with questions or suggestions. Happy coding! 🚀