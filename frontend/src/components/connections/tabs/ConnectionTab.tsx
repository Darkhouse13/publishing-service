'use client';

import { useState, FormEvent } from 'react';
import Input from '@/components/ui/Input';
import Button from '@/components/ui/Button';
import type { Blog } from '@/lib/types';

interface ConnectionTabProps {
  blog: Blog;
  onSave: (data: Partial<Blog>) => Promise<void>;
}

export default function ConnectionTab({ blog, onSave }: ConnectionTabProps) {
  const [name, setName] = useState(blog.name);
  const [url, setUrl] = useState(blog.url);
  const [wpUsername, setWpUsername] = useState(blog.wp_username);
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setIsSaving(true);
    setSaveError(null);
    setSaveSuccess(false);

    try {
      await onSave({
        name: name.trim(),
        url: url.trim(),
        wp_username: wpUsername.trim(),
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
        Connection Details
      </h2>

      <div className="max-w-xl space-y-5">
        <Input
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Blog name"
        />
        <Input
          label="URL"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://myblog.com"
        />
        <Input
          label="WP Username"
          value={wpUsername}
          onChange={(e) => setWpUsername(e.target.value)}
          placeholder="admin"
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
