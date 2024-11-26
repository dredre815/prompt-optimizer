'use client';

import { useState, useEffect } from 'react';
import { XMarkIcon, KeyIcon, ShieldCheckIcon } from '@heroicons/react/24/solid';
import toast from 'react-hot-toast';

export default function Settings({ isOpen, onClose }) {
  const [openaiKey, setOpenaiKey] = useState('');
  const [anthropicKey, setAnthropicKey] = useState('');

  useEffect(() => {
    const savedOpenaiKey = localStorage.getItem('openai_api_key');
    const savedAnthropicKey = localStorage.getItem('anthropic_api_key');
    if (savedOpenaiKey) setOpenaiKey(savedOpenaiKey);
    if (savedAnthropicKey) setAnthropicKey(savedAnthropicKey);
  }, []);

  const handleSave = () => {
    if (openaiKey) localStorage.setItem('openai_api_key', openaiKey);
    if (anthropicKey) localStorage.setItem('anthropic_api_key', anthropicKey);
    toast.success('Settings saved successfully');
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-2xl bg-card p-6 shadow-2xl sm:p-8">
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <KeyIcon className="h-6 w-6 text-primary" />
            <h2 className="text-2xl font-bold text-card-foreground">API Settings</h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-full p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <XMarkIcon className="h-6 w-6" />
          </button>
        </div>

        <div className="mb-8 flex items-start space-x-3 rounded-lg bg-primary/5 p-4">
          <ShieldCheckIcon className="mt-1 h-5 w-5 flex-shrink-0 text-primary" />
          <div>
            <h3 className="font-medium text-primary">Secure Storage</h3>
            <p className="text-sm text-primary/80">
              Your API keys are stored securely in your browser&apos;s local storage and are never sent to any server.
              They are only used to make direct API calls to OpenAI and Anthropic.
            </p>
          </div>
        </div>
        
        <div className="space-y-6">
          <div>
            <label htmlFor="openai" className="mb-2 block text-base font-medium text-card-foreground">
              OpenAI API Key
            </label>
            <div className="relative">
              <input
                type="password"
                id="openai"
                value={openaiKey}
                onChange={(e) => setOpenaiKey(e.target.value)}
                className="w-full rounded-xl border-2 border-input bg-background px-4 py-3 pl-11 text-foreground shadow-sm transition-all hover:border-muted focus:border-primary focus:outline-none focus:ring-4 focus:ring-primary/20"
                placeholder="sk-..."
              />
              <KeyIcon className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground" />
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              Required for GPT-4o. Get your API key from{' '}
              <a
                href="https://platform.openai.com/api-keys"
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                OpenAI&apos;s platform
              </a>
            </p>
          </div>

          <div>
            <label htmlFor="anthropic" className="mb-2 block text-base font-medium text-card-foreground">
              Anthropic API Key
            </label>
            <div className="relative">
              <input
                type="password"
                id="anthropic"
                value={anthropicKey}
                onChange={(e) => setAnthropicKey(e.target.value)}
                className="w-full rounded-xl border-2 border-input bg-background px-4 py-3 pl-11 text-foreground shadow-sm transition-all hover:border-muted focus:border-primary focus:outline-none focus:ring-4 focus:ring-primary/20"
                placeholder="sk-ant-..."
              />
              <KeyIcon className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground" />
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              Required for Claude 3.5 Sonnet. Get your API key from{' '}
              <a
                href="https://console.anthropic.com/settings/keys"
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                Anthropic&apos;s console
              </a>
            </p>
          </div>
        </div>

        <div className="mt-8 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="rounded-xl bg-secondary px-5 py-2.5 text-base font-medium text-secondary-foreground transition-colors hover:bg-secondary/80"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="rounded-xl bg-primary px-5 py-2.5 text-base font-medium text-primary-foreground shadow-lg transition-all hover:bg-primary/90 hover:shadow-xl"
          >
            Save Settings
          </button>
        </div>
      </div>
    </div>
  );
} 