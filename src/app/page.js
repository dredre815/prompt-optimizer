'use client';

import { useState } from 'react';
import { Cog6ToothIcon, SparklesIcon } from '@heroicons/react/24/solid';
import { Toaster, toast } from 'react-hot-toast';
import PromptForm from './components/PromptForm';
import Settings from './components/Settings';
import ThemeToggle from './components/ThemeToggle';
import { optimizePrompt } from './utils/api';

export default function Home() {
  const [isLoading, setIsLoading] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [optimizedPrompt, setOptimizedPrompt] = useState('');

  const handleOptimize = async (prompt, model) => {
    setIsLoading(true);
    try {
      const result = await optimizePrompt(prompt, model);
      setOptimizedPrompt(result);
    } catch (error) {
      toast.error(error.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-sky-50 via-background to-background dark:from-sky-900 px-4 pb-8 pt-16 sm:px-6 lg:px-8">
      <div className="absolute inset-0 bg-grid-slate-100 [mask-image:linear-gradient(0deg,white,rgba(255,255,255,0.6))] dark:bg-grid-slate-700/25 dark:[mask-image:linear-gradient(0deg,rgba(255,255,255,0.1),rgba(255,255,255,0.5))]" />
      <Toaster position="top-center" />
      
      <div className="fixed right-4 top-4 z-50 flex items-center gap-2 sm:right-6 sm:top-6">
        <ThemeToggle />
        <button
          onClick={() => setShowSettings(true)}
          className="glass-effect rounded-full p-3 shadow-lg transition-all duration-300 hover:scale-110 hover:shadow-xl"
          title="API Settings"
        >
          <Cog6ToothIcon className="h-6 w-6 text-muted-foreground" />
        </button>
      </div>

      <div className="relative mx-auto max-w-5xl">
        <div className="mb-12 text-center">
          <div className="mb-4 flex items-center justify-center space-x-2">
            <SparklesIcon className="h-8 w-8 animate-pulse text-primary sm:h-10 sm:w-10" />
            <h1 className="animate-gradient bg-gradient-to-r from-foreground via-primary to-foreground bg-clip-text bg-[length:200%_auto] text-4xl font-bold tracking-tight text-transparent sm:text-5xl md:text-6xl">
              Prompt Optimizer
            </h1>
          </div>
          <p className="mx-auto max-w-2xl text-lg text-muted-foreground sm:text-xl">
            Transform your natural language prompts into optimized, machine-readable instructions for better AI responses
          </p>
        </div>

        <div className="mb-8 overflow-hidden rounded-2xl bg-card/80 p-6 backdrop-blur-sm transition-all duration-300 hover:bg-card/90 hover:shadow-lg sm:p-8">
          <div className="mb-8">
            <h2 className="mb-4 text-xl font-semibold text-card-foreground">How it works</h2>
            <div className="grid gap-6 sm:grid-cols-3">
              <div className="group rounded-xl bg-secondary p-4 transition-all duration-300 hover:scale-105 hover:shadow-lg">
                <div className="mb-2 text-lg font-medium text-secondary-foreground">1. Enter Your Prompt</div>
                <p className="text-secondary-foreground/80">
                  Write what you want the AI to do in your own words - no special formatting needed
                </p>
              </div>
              <div className="group rounded-xl bg-secondary p-4 transition-all duration-300 hover:scale-105 hover:shadow-lg">
                <div className="mb-2 text-lg font-medium text-secondary-foreground">2. Choose Model</div>
                <p className="text-secondary-foreground/80">
                  Select between GPT-4o or Claude 3.5 Sonnet to optimize your prompt specifically for that model
                </p>
              </div>
              <div className="group rounded-xl bg-secondary p-4 transition-all duration-300 hover:scale-105 hover:shadow-lg">
                <div className="mb-2 text-lg font-medium text-secondary-foreground">3. Get Results</div>
                <p className="text-secondary-foreground/80">
                  Receive an optimized version that helps the AI better understand your requirements
                </p>
              </div>
            </div>
          </div>
          
          <PromptForm onSubmit={handleOptimize} isLoading={isLoading} />
        </div>

        {optimizedPrompt && (
          <div className="overflow-hidden rounded-2xl bg-card/80 p-6 backdrop-blur-sm transition-all duration-300 hover:bg-card/90 hover:shadow-lg sm:p-8">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-xl font-semibold text-card-foreground">Optimized Prompt</h2>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(optimizedPrompt);
                  toast.success('Copied to clipboard!');
                }}
                className="flex items-center space-x-1 rounded-lg bg-primary/10 px-4 py-2 text-sm font-medium text-primary transition-all duration-300 hover:scale-105 hover:bg-primary/20"
              >
                <span>Copy</span>
              </button>
            </div>
            <div className="rounded-lg bg-muted p-4 font-mono text-sm transition-all duration-300 hover:bg-muted/70">
              <pre className="whitespace-pre-wrap text-muted-foreground">{optimizedPrompt}</pre>
            </div>
            <div className="mt-4">
              <p className="text-sm text-muted-foreground">
                This optimized version is structured to provide clearer instructions and better context for the AI model.
                Copy and use it in your AI interactions for improved results.
              </p>
            </div>
          </div>
        )}
      </div>

      <Settings isOpen={showSettings} onClose={() => setShowSettings(false)} />

      <style jsx global>{`
        @keyframes gradient {
          0% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
          100% { background-position: 0% 50%; }
        }
        .animate-gradient {
          animation: gradient 6s linear infinite;
        }
      `}</style>
    </div>
  );
}