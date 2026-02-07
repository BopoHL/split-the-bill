import axios from 'axios';
import { getTelegramWebApp } from '../telegram/init';

// Create axios instance with base configuration
const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000,
});

// Request interceptor to add Telegram auth data
apiClient.interceptors.request.use(
  (config) => {
    const webApp = getTelegramWebApp();
    
    if (webApp?.initData) {
      // Add Telegram initData to headers for backend validation
      config.headers['X-Telegram-Init-Data'] = webApp.initData;
    }
    
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    if (error.response) {
      // Server responded with error status
      const message = error.response.data?.detail || error.response.data?.message || 'An error occurred';
      console.error('API Error:', message);
      
      // You can add toast notifications here
      // toast.error(message);
    } else if (error.request) {
      // Request was made but no response received
      console.error('Network Error:', error.message);
      // toast.error('Network error. Please check your connection.');
    } else {
      // Something else happened
      console.error('Error:', error.message);
    }
    
    return Promise.reject(error);
  }
);

export default apiClient;
