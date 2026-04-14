'use client';

import { useState, useMemo, FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { PageHeader } from '@/components/layout';
import Select from '@/components/ui/Select';
import Textarea from '@/components/ui/Textarea';
import Button from '@/components/ui/Button';
import { useBlogs } from '@/hooks/useBlogs';
import { useRuns } from '@/hooks/useRuns';

interface FormErrors {
  blog_id?: string;
  keywords?: string;
}

export default function NewRunPage() {
  const router = useRouter();
  const { blogs } = useBlogs();
  const { createRun } = useRuns();

  const [selectedBlogId, setSelectedBlogId] = useState('');
  const [keywordsText, setKeywordsText] = useState('');
  const [errors, setErrors] = useState<FormErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Build blog options for dropdown
  const blogOptions = useMemo(
    () => [
      { value: '', label: 'Select a blog...' },
      ...blogs.map((blog) => ({ value: blog.id, label: blog.name })),
    ],
    [blogs],
  );

  function validate(): FormErrors {
    const newErrors: FormErrors = {};

    if (!selectedBlogId) {
      newErrors.blog_id = 'Please select a blog';
    }

    const keywords = keywordsText
      .split(',')
      .map((k) => k.trim())
      .filter(Boolean);

    if (keywords.length === 0) {
      newErrors.keywords = 'At least one keyword is required';
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

    const keywords = keywordsText
      .split(',')
      .map((k) => k.trim())
      .filter(Boolean);

    setIsSubmitting(true);
    try {
      const newRun = await createRun({
        blog_id: selectedBlogId,
        keywords,
      });
      router.push(`/runs/${newRun.id}`);
    } catch (err) {
      setIsSubmitting(false);
      setSubmitError(
        err instanceof Error ? err.message : 'Failed to create run. Please try again.',
      );
    }
  }

  return (
    <div>
      <PageHeader title="New Run">
        <Link href="/runs">
          <Button type="button" variant="secondary">
            ← Back
          </Button>
        </Link>
      </PageHeader>

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

          {/* Blog Selector */}
          <div className="mb-6">
            <Select
              label="Blog"
              options={blogOptions}
              value={selectedBlogId}
              onChange={(e) => {
                setSelectedBlogId(e.target.value);
                if (errors.blog_id) {
                  setErrors((prev) => ({ ...prev, blog_id: undefined }));
                }
              }}
              error={errors.blog_id}
            />
          </div>

          {/* Keywords Input */}
          <div className="mb-8">
            <Textarea
              label="Keywords"
              placeholder="Enter keywords separated by commas, e.g.: patio furniture, outdoor decor, garden design"
              value={keywordsText}
              onChange={(e) => {
                setKeywordsText(e.target.value);
                if (errors.keywords) {
                  setErrors((prev) => ({ ...prev, keywords: undefined }));
                }
              }}
              rows={4}
              error={errors.keywords}
            />
            <p className="mt-2 text-xs font-bold text-muted uppercase tracking-widest">
              Separate keywords with commas
            </p>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-4 border-t-[3px] border-base pt-6">
            <Button type="submit" variant="primary" disabled={isSubmitting}>
              {isSubmitting ? 'Starting Run...' : 'Start Run'}
            </Button>
            <Link href="/runs">
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
