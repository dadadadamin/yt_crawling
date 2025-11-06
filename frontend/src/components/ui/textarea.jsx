import React from 'react';

export const Textarea = ({ 
  placeholder = '', 
  value, 
  onChange, 
  rows = 4,
  className = '' 
}) => {
  return (
    <textarea
      placeholder={placeholder}
      value={value}
      onChange={onChange}
      rows={rows}
      className={`px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-y ${className}`}
    />
  );
};

