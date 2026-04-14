'use client';

import { useState, FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { PageHeader } from '@/components/layout';
import Input from '@/components/ui/Input';
import Textarea from '@/components/ui/Textarea';
import Button from '@/components/ui/Button';
import { blogsApi } from '@/lib/api';
import type { BlogCreate } from '@/lib/types';

interface FormErrors {
  [key: string]: string;
}

export default function NewBlogPage() {
  const router = useRouter();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [errors, setErrors] = useState<FormErrors>({});

  // Form state
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [wpUsername, setWpUsername] = useState('');
  const [wpApplicationPassword, setWpApplicationPassword] = useState('');
  const [profilePrompt, setProfilePrompt] = useState('');
  const [fallbackCategory, setFallbackCategory] = useState('');
  const [deprioritizedCategory, setDeprioritizedCategory] = useState('');
  const [seedKeywords, setSeedKeywords] = useState('');
  const [pinterestBoardMap, setPinterestBoardMap] = useState('');
  const [categoryKeywords, setCategoryKeywords] = useState('');

  function validate(): FormErrors {
    const newErrors: FormErrors = {};

    if (!name.trim()) {
      newErrors.name = 'Name is required';
    }
    if (!url.trim()) {
      newErrors.url = 'URL is required';
    }
    if (!wpUsername.trim()) {
      newErrors.wp_username = 'WP Username is required';
    }
    if (!wpApplicationPassword.trim()) {
      newErrors.wp_application_password = 'WP Application Password is required';
    }

    return newErrors;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitError(null);

    const validationErrors = validate();
    setErrors(validationErrors);

    if (Object.keys(validationErrors).length > 0) {
      return;
    }

    // Parse textarea fields into structured data
    const parsedSeedKeywords = seedKeywords.trim()
      ? seedKeywords.split(',').map((k) => k.trim()).filter(Boolean)
      : undefined;

    let parsedPinterestBoardMap: Record<string, string> | undefined;
    if (pinterestBoardMap.trim()) {
      parsedPinterestBoardMap = {};
      pinterestBoardMap.split('\n').forEach((line) => {
        const [key, value] = line.split('=').map((s) => s.trim());
        if (key && value) {
          parsedPinterestBoardMap![key] = value;
        }
      });
    }

    let parsedCategoryKeywords: Record<string, string[]> | undefined;
    if (categoryKeywords.trim()) {
      parsedCategoryKeywords = {};
      categoryKeywords.split('\n').forEach((line) => {
        const [category, keywords] = line.split('=').map((s) => s.trim());
        if (category && keywords) {
          parsedCategoryKeywords![category] = keywords.split(',').map((k) => k.trim()).filter(Boolean);
        }
      });
    }

    const payload: BlogCreate = {
      name: name.trim(),
      url: url.trim(),
      wp_username: wpUsername.trim(),
      wp_application_password: wpApplicationPassword.trim(),
      ...(profilePrompt.trim() && { profile_prompt: profilePrompt.trim() }),
      ...(fallbackCategory.trim() && { fallback_category: fallbackCategory.trim() }),
      ...(deprioritizedCategory.trim() && { deprioritized_category: deprioritizedCategory.trim() }),
      ...(parsedSeedKeywords && { seed_keywords: parsedSeedKeywords }),
      ...(parsedPinterestBoardMap && { pinterest_board_map: parsedPinterestBoardMap }),
      ...(parsedCategoryKeywords && { category_keywords: parsedCategoryKeywords }),
    };

    setIsSubmitting(true);
    try {
      await blogsApi.create(payload);
      router.push('/connections');
    } catch (err) {
      setIsSubmitting(false);
      setSubmitError(
        err instanceof Error ? err.message : 'Failed to create blog. Please try again.'
      );
    }
  }

  return (
    <div>
      <PageHeader title="Add New Blog" />

      <div className="p-8">
        <form onSubmit={handleSubmit} className="max-w-2xl">
          {/* Server error */}
          {submitError && (
            <div className="mb-6 border-[3px] border-error bg-error/5 p-4">
              <p className="text-sm font-bold text-error uppercase tracking-widest">
                {submitError}
              </p>
            </div>
          )}

          {/* Required Fields Section */}
          <div className="mb-8">
            <h2 className="text-lg font-black uppercase tracking-widest mb-4">
              Connection Details
            </h2>
            <div className="space-y-5">
              <Input
                label="Name"
                placeholder="My Blog Name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                error={errors.name}
              />
              <Input
                label="URL"
                placeholder="https://myblog.com"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                error={errors.url}
              />
              <Input
                label="WP Username"
                placeholder="admin"
                value={wpUsername}
                onChange={(e) => setWpUsername(e.target.value)}
                error={errors.wp_username}
              />
              <Input
                label="WP Application Password"
                type="password"
                placeholder="Application password from WordPress"
                value={wpApplicationPassword}
                onChange={(e) => setWpApplicationPassword(e.target.value)}
                error={errors.wp_application_password}
              />
            </div>
          </div>

          {/* AI Personality Section */}
          <div className="mb-8">
            <h2 className="text-lg font-black uppercase tracking-widest mb-4">
              AI Personality
            </h2>
            <Textarea
              label="Profile Prompt"
              placeholder="Write in a warm, conversational tone about..."
              value={profilePrompt}
              onChange={(e) => setProfilePrompt(e.target.value)}
              rows={4}
            />
          </div>

          {/* Categories Section */}
          <div className="mb-8">
            <h2 className="text-lg font-black uppercase tracking-widest mb-4">
              Categories
            </h2>
            <div className="space-y-5">
              <Input
                label="Fallback Category"
                placeholder="Uncategorized"
                value={fallbackCategory}
                onChange={(e) => setFallbackCategory(e.target.value)}
              />
              <Input
                label="Deprioritized Category"
                placeholder="Uncategorized"
                value={deprioritizedCategory}
                onChange={(e) => setDeprioritizedCategory(e.target.value)}
              />
              <Textarea
                label="Category Keywords"
                placeholder={"Category Name = keyword1, keyword2, keyword3\nAnother Category = keyword4, keyword5"}
                value={categoryKeywords}
                onChange={(e) => setCategoryKeywords(e.target.value)}
                rows={4}
              />
            </div>
          </div>

          {/* Pinterest Section */}
          <div className="mb-8">
            <h2 className="text-lg font-black uppercase tracking-widest mb-4">
              Pinterest
            </h2>
            <div className="space-y-5">
              <Textarea
                label="Seed Keywords"
                placeholder="keyword1, keyword2, keyword3"
                value={seedKeywords}
                onChange={(e) => setSeedKeywords(e.target.value)}
                rows={2}
              />
              <Textarea
                label="Pinterest Board Map"
                placeholder={"Category Name = board-slug\nAnother Category = another-board-slug"}
                value={pinterestBoardMap}
                onChange={(e) => setPinterestBoardMap(e.target.value)}
                rows={3}
              />
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-4 border-t-[3px] border-base pt-6">
            <Button type="submit" variant="primary" disabled={isSubmitting}>
              {isSubmitting ? 'Saving...' : 'Save Connection'}
            </Button>
            <Link href="/connections">
              <Button type="button" variant="secondary">
                Cancel
              </Button>
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
