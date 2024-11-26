'use client';

import { useState } from 'react';
import { ArrowPathIcon, BeakerIcon, CommandLineIcon } from '@heroicons/react/24/solid';
import toast from 'react-hot-toast';

export default function PromptForm({ onSubmit, isLoading }) {
  const [prompt, setPrompt] = useState('');
  const [model, setModel] = useState('gpt-4o');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!prompt.trim()) {
      toast.error('Please enter a prompt');
      return;
    }
    onSubmit(prompt, model);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="space-y-6">
        <div className="group">
          <label htmlFor="model" className="mb-2 block text-base font-medium text-foreground">
            Select AI Model
          </label>
          <div className="relative">
            <select
              id="model"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full appearance-none rounded-xl border-2 border-input bg-background px-4 py-3 pl-11 pr-10 text-foreground shadow-sm transition-all duration-300 hover:border-primary/50 focus:border-primary focus:outline-none focus:ring-4 focus:ring-primary/20"
            >
              <option value="gpt-4o">GPT-4o (OpenAI)</option>
              <option value="claude-3.5-sonnet">Claude 3.5 Sonnet (Anthropic)</option>
            </select>
            <BeakerIcon className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground transition-colors duration-300 group-hover:text-primary/70" />
            <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-muted-foreground transition-colors duration-300 group-hover:text-primary/70">
              <svg className="h-5 w-5 fill-current" viewBox="0 0 20 20">
                <path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" />
              </svg>
            </div>
          </div>
          <p className="mt-2 text-sm text-muted-foreground transition-colors duration-300 group-hover:text-foreground/70">
            Choose the AI model you want to optimize your prompt for
          </p>
        </div>

        <div className="group">
          <label htmlFor="prompt" className="mb-2 block text-base font-medium text-foreground">
            Your Prompt
          </label>
          <div className="relative">
            <textarea
              id="prompt"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Example: Write a story about a magical forest that teaches children about the importance of environmental conservation..."
              className="min-h-[160px] w-full rounded-xl border-2 border-input bg-background px-4 py-3 pl-11 text-foreground shadow-sm transition-all duration-300 hover:border-primary/50 focus:border-primary focus:outline-none focus:ring-4 focus:ring-primary/20"
            />
            <CommandLineIcon className="pointer-events-none absolute left-3 top-3 h-5 w-5 text-muted-foreground transition-colors duration-300 group-hover:text-primary/70" />
          </div>
          <p className="mt-2 text-sm text-muted-foreground transition-colors duration-300 group-hover:text-foreground/70">
            Describe what you want the AI to do in natural language. Be as specific or general as you like - we'll help optimize it.
          </p>
        </div>
      </div>

      <button
        type="submit"
        disabled={isLoading}
        className="group relative w-full overflow-hidden rounded-xl bg-primary px-4 py-3 text-lg font-medium text-primary-foreground shadow-lg transition-all duration-300 hover:scale-[1.02] hover:shadow-xl disabled:bg-primary/50"
      >
        <span className={`flex items-center justify-center transition-opacity duration-300 ${isLoading ? 'opacity-0' : 'opacity-100'}`}>
          Transform Your Prompt
          <svg
            className="ml-2 h-5 w-5 transition-transform duration-300 group-hover:translate-x-1"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
          </svg>
        </span>
        {isLoading && (
          <span className="absolute inset-0 flex items-center justify-center">
            <ArrowPathIcon className="mr-2 h-5 w-5 animate-spin" />
            <span>Optimizing your prompt...</span>
          </span>
        )}
      </button>
    </form>
  );
} 