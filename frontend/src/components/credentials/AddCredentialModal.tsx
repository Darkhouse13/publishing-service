'use client';

import { useState } from 'react';
import Button from '@/components/ui/Button';
import Input from '@/components/ui/Input';
import Select from '@/components/ui/Select';
import type { Credential, CredentialCreate } from '@/lib/types';

interface AddCredentialModalProps {
  credential?: Credential | null;
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: CredentialCreate) => Promise<void>;
}

const PROVIDER_OPTIONS = [
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'fal', label: 'FAL' },
  { value: 'brave', label: 'Brave' },
  { value: 'pinclicks', label: 'PinClicks' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'google', label: 'Google' },
];

export default function AddCredentialModal({
  credential,
  isOpen,
  onClose,
  onSubmit,
}: AddCredentialModalProps) {
  const isEditing = !!credential;

  const [provider, setProvider] = useState(credential?.provider ?? '');
  const [keyName, setKeyName] = useState(credential?.key_name ?? '');
  const [value, setValue] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) return null;

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!provider.trim()) {
      newErrors.provider = 'Provider is required';
    }
    if (!keyName.trim()) {
      newErrors.keyName = 'Key name is required';
    }
    if (!isEditing && !value.trim()) {
      newErrors.value = 'Secret value is required';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validate()) return;

    setIsSubmitting(true);
    try {
      await onSubmit({
        provider: provider.trim(),
        key_name: keyName.trim(),
        value: value.trim(),
      });
      // Reset form
      setProvider('');
      setKeyName('');
      setValue('');
      setErrors({});
      onClose();
    } catch {
      setErrors({ value: 'Failed to save credential. Please try again.' });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    if (!isSubmitting) {
      setErrors({});
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white border-[3px] border-base shadow-solid-lg w-full max-w-lg mx-4 rounded-none">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b-[3px] border-base">
          <h2 className="font-black uppercase tracking-widest text-lg">
            {isEditing ? 'Update Credential' : 'Add Credential'}
          </h2>
          <button
            onClick={handleClose}
            className="font-black text-xl leading-none hover:text-error transition-colors px-2"
            disabled={isSubmitting}
          >
            ✕
          </button>
        </div>

        {/* Modal Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {isEditing ? (
            <div className="space-y-1">
              <label className="block font-black uppercase tracking-widest text-xs text-base mb-2">
                Provider
              </label>
              <div className="border-[3px] border-base p-4 font-bold bg-panel rounded-none">
                {credential.provider.toUpperCase()}
              </div>
            </div>
          ) : (
            <Select
              label="Provider"
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              options={PROVIDER_OPTIONS}
              placeholder="Select provider..."
              error={errors.provider}
              disabled={isSubmitting}
            />
          )}

          {isEditing ? (
            <div className="space-y-1">
              <label className="block font-black uppercase tracking-widest text-xs text-base mb-2">
                Key Name
              </label>
              <div className="border-[3px] border-base p-4 font-bold bg-panel rounded-none">
                {credential.key_name}
              </div>
            </div>
          ) : (
            <Input
              label="Key Name"
              value={keyName}
              onChange={(e) => setKeyName(e.target.value)}
              placeholder="e.g. DEEPSEEK_API_KEY"
              error={errors.keyName}
              disabled={isSubmitting}
            />
          )}

          <Input
            label={isEditing ? 'New Secret Value' : 'Secret Value'}
            type="password"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={isEditing ? 'Enter new value to update' : 'Enter API key or secret'}
            error={errors.value}
            disabled={isSubmitting}
          />

          {isEditing && (
            <p className="text-xs font-bold text-muted uppercase tracking-widest">
              Leave empty to keep the current value unchanged.
            </p>
          )}

          {/* Modal Footer */}
          <div className="flex items-center justify-end gap-3 pt-4 border-t-[3px] border-base">
            <Button
              variant="secondary"
              type="button"
              onClick={handleClose}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              type="submit"
              disabled={isSubmitting}
            >
              {isSubmitting
                ? 'Saving...'
                : isEditing
                  ? 'Update Credential'
                  : 'Add Credential'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
