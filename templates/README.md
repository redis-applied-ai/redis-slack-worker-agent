# Templates

This directory contains HTML templates for the web interface of the Content Management System.

## Files

- `home.html` - Main landing page with Auth0 login/logout functionality
- `content.html` - Content management interface for interacting with the API

## Features

### Home Page (`home.html`)
- Auth0 authentication integration
- Session management
- User information display
- Navigation to content management

### Content Management Page (`content.html`)
- Interactive forms for all content API endpoints:
  - Add content
  - Update content
  - Remove content
  - Get content status
  - Get ledger summary
  - Trigger content processing
- Real-time API interaction with JavaScript
- Responsive design with modern styling

## Usage

1. Navigate to `http://localhost:8000/` to access the home page
2. Click "Login with Auth0" to authenticate
3. After login, click "Go to Content API" to access the content management interface
4. Use the forms to interact with the content management API

## Environment Variables Required

Make sure these environment variables are set for Auth0 integration:

- `AUTH0_DOMAIN` - Your Auth0 domain
- `AUTH0_AUDIENCE` - Your Auth0 API audience
- `AUTH0_CLIENT_ID` - Your Auth0 application client ID
- `AUTH0_CLIENT_SECRET` - Your Auth0 application client secret

## Notes

- The templates use a simplified Auth0 integration for demonstration purposes
- In production, consider using a more robust OAuth2 library
- Session storage is currently in-memory; use Redis or similar for production
- The content API requires proper authentication tokens
