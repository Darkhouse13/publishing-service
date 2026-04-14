'use client';

import { useState, FormEvent } from 'react';
import Input from '@/components/ui/Input';
import Select from '@/components/ui/Select';
import Textarea from '@/components/ui/Textarea';
import Button from '@/components/ui/Button';
import type { Blog } from '@/lib/types';

interface AIPersonalityTabProps {
  blog: Blog;
  onSave: (data: Partial<Blog>) => Promise<void>;
}

export default function AIPersonalityTab({ blog, onSave }: AIPersonalityTabProps) {
  const [llmProvider, setLlmProvider] = useState('');
  const [llmModel, setLlmModel] = useState('');
  const [imageProvider, setImageProvider] = useState('');
  const [imageModel, setImageModel] = useState('');
  const [profilePrompt, setProfilePrompt] = useState(blog.profile_prompt || '');
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // These fields come from pipeline config, not blog directly.
  // We provide sensible defaults for the form.
  // The blog only has profile_prompt; the LLM/image fields are
  // populated when the user enters them (they're stored in pipeline config
  // but shown here for convenience).

  const llmProviderOptions = [
    { value: 'deepseek', label: 'DeepSeek' },
    { value: 'openai', label: 'OpenAI' },
    { value: 'anthropic', label: 'Anthropic' },
    { value: 'google', label: 'Google' },
  ];

  const imageProviderOptions = [
    { value: 'fal', label: 'FAL' },
    { value: 'openai', label: 'OpenAI (DALL-E)' },
    { value: 'stability', label: 'Stability AI' },
  ];

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setIsSaving(true);
    setSaveError(null);
    setSaveSuccess(false);

    try {
      await onSave({
        profile_prompt: profilePrompt.trim(),
      });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    } catch (err) {
      setSaveError(
        err instanceof Error ? err.message : 'Failed to save changes.'
      );
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <h2 className="text-lg font-black uppercase tracking-widest mb-6">
        AI Personality
      </h2>

      <div className="max-w-xl space-y-5">
        <Select
          label="LLM Provider"
          options={llmProviderOptions}
          value={llmProvider}
          onChange={(e) => setLlmProvider(e.target.value)}
          placeholder="Select provider"
        />
        <Input
          label="LLM Model"
          value={llmModel}
          onChange={(e) => setLlmModel(e.target.value)}
          placeholder="e.g. deepseek-chat"
        />
        <Select
          label="Image Provider"
          options={imageProviderOptions}
          value={imageProvider}
          onChange={(e) => setImageProvider(e.target.value)}
          placeholder="Select provider"
        />
        <Input
          label="Image Model"
          value={imageModel}
          onChange={(e) => setImageModel(e.target.value)}
          placeholder="e.g. fal-ai/flux/dev"
        />
        <Textarea
          label="Profile Prompt"
          value={profilePrompt}
          onChange={(e) => setProfilePrompt(e.target.value)}
          placeholder="Write in a warm, conversational tone about..."
          rows={6}
        />
      </div>

      {/* Feedback */}
      {saveError && (
        <div className="mt-4 border-[3px] border-error bg-error/5 p-4">
          <p className="text-sm font-bold text-error uppercase tracking-widest">
            {saveError}
          </p>
        </div>
      )}
      {saveSuccess && (
        <div className="mt-4 border-[3px] border-accent bg-accent/10 p-4">
          <p className="text-sm font-bold text-base uppercase tracking-widest">
            Changes saved successfully
          </p>
        </div>
      )}

      <div className="mt-6 flex items-center gap-4">
        <Button type="submit" variant="primary" disabled={isSaving}>
          {isSaving ? 'Saving...' : 'Save Changes'}
        </Button>
      </div>
    </form>
  );
}
