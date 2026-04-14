'use client';

import { useState, FormEvent } from 'react';
import Input from '@/components/ui/Input';
import Select from '@/components/ui/Select';
import Button from '@/components/ui/Button';
import type { PipelineConfig } from '@/lib/types';

interface PipelineTabProps {
  pipelineConfig: PipelineConfig | null;
  isLoading: boolean;
  onSave: (data: Partial<PipelineConfig>) => Promise<void>;
}

export default function PipelineTab({
  pipelineConfig,
  isLoading,
  onSave,
}: PipelineTabProps) {
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Form state — initialized from pipelineConfig
  const [llmProvider, setLlmProvider] = useState(
    pipelineConfig?.llm_provider || ''
  );
  const [llmModel, setLlmModel] = useState(
    pipelineConfig?.llm_model || ''
  );
  const [imageProvider, setImageProvider] = useState(
    pipelineConfig?.image_provider || ''
  );
  const [imageModel, setImageModel] = useState(
    pipelineConfig?.image_model || ''
  );
  const [trendsRegion, setTrendsRegion] = useState(
    pipelineConfig?.trends_region || ''
  );
  const [trendsRange, setTrendsRange] = useState(
    pipelineConfig?.trends_range || ''
  );
  const [trendsTopN, setTrendsTopN] = useState(
    pipelineConfig?.trends_top_n?.toString() || ''
  );
  const [pinclicksMaxRecords, setPinclicksMaxRecords] = useState(
    pipelineConfig?.pinclicks_max_records?.toString() || ''
  );
  const [winnersCount, setWinnersCount] = useState(
    pipelineConfig?.winners_count?.toString() || ''
  );
  const [publishStatus, setPublishStatus] = useState(
    pipelineConfig?.publish_status || ''
  );
  const [csvCadenceMinutes, setCsvCadenceMinutes] = useState(
    pipelineConfig?.csv_cadence_minutes?.toString() || ''
  );
  const [pinTemplateMode, setPinTemplateMode] = useState(
    pipelineConfig?.pin_template_mode || ''
  );
  const [maxConcurrentArticles, setMaxConcurrentArticles] = useState(
    pipelineConfig?.max_concurrent_articles?.toString() || ''
  );

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

  const trendsRegionOptions = [
    { value: 'US', label: 'US' },
    { value: 'GLOBAL', label: 'Global' },
    { value: 'GB', label: 'United Kingdom' },
    { value: 'CA', label: 'Canada' },
    { value: 'AU', label: 'Australia' },
  ];

  const trendsRangeOptions = [
    { value: '3m', label: '3 Months' },
    { value: '6m', label: '6 Months' },
    { value: '12m', label: '12 Months' },
  ];

  const publishStatusOptions = [
    { value: 'draft', label: 'Draft' },
    { value: 'publish', label: 'Publish' },
  ];

  const pinTemplateModeOptions = [
    { value: 'center_strip', label: 'Center Strip' },
    { value: 'bold_header', label: 'Bold Header' },
    { value: 'minimal', label: 'Minimal' },
  ];

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setIsSaving(true);
    setSaveError(null);
    setSaveSuccess(false);

    try {
      const data: Record<string, unknown> = {};

      if (llmProvider) data.llm_provider = llmProvider;
      if (llmModel) data.llm_model = llmModel;
      if (imageProvider) data.image_provider = imageProvider;
      if (imageModel) data.image_model = imageModel;
      if (trendsRegion) data.trends_region = trendsRegion;
      if (trendsRange) data.trends_range = trendsRange;
      if (trendsTopN) data.trends_top_n = parseInt(trendsTopN, 10);
      if (pinclicksMaxRecords)
        data.pinclicks_max_records = parseInt(pinclicksMaxRecords, 10);
      if (winnersCount) data.winners_count = parseInt(winnersCount, 10);
      if (publishStatus) data.publish_status = publishStatus;
      if (csvCadenceMinutes)
        data.csv_cadence_minutes = parseInt(csvCadenceMinutes, 10);
      if (pinTemplateMode) data.pin_template_mode = pinTemplateMode;
      if (maxConcurrentArticles)
        data.max_concurrent_articles = parseInt(maxConcurrentArticles, 10);

      await onSave(data);
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

  // Loading skeleton
  if (isLoading) {
    return (
      <div>
        <h2 className="text-lg font-black uppercase tracking-widest mb-6">
          Pipeline Configuration
        </h2>
        <div className="max-w-xl space-y-5">
          {Array.from({ length: 11 }).map((_, i) => (
            <div key={i} className="space-y-2">
              <div className="h-4 bg-panel animate-pulse w-32" />
              <div className="h-12 bg-panel animate-pulse" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit}>
      <h2 className="text-lg font-black uppercase tracking-widest mb-6">
        Pipeline Configuration
      </h2>

      <div className="max-w-xl space-y-5">
        <div className="grid grid-cols-2 gap-5">
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
        </div>

        <div className="grid grid-cols-2 gap-5">
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
        </div>

        <div className="border-t-[3px] border-base pt-5">
          <h3 className="text-sm font-black uppercase tracking-widest mb-4 text-muted">
            Trends Configuration
          </h3>
          <div className="grid grid-cols-3 gap-5">
            <Select
              label="Trends Region"
              options={trendsRegionOptions}
              value={trendsRegion}
              onChange={(e) => setTrendsRegion(e.target.value)}
              placeholder="Region"
            />
            <Select
              label="Trends Range"
              options={trendsRangeOptions}
              value={trendsRange}
              onChange={(e) => setTrendsRange(e.target.value)}
              placeholder="Range"
            />
            <Input
              label="Trends Top N"
              type="number"
              value={trendsTopN}
              onChange={(e) => setTrendsTopN(e.target.value)}
              placeholder="15"
            />
          </div>
        </div>

        <div className="border-t-[3px] border-base pt-5">
          <h3 className="text-sm font-black uppercase tracking-widest mb-4 text-muted">
            Analysis Configuration
          </h3>
          <div className="grid grid-cols-2 gap-5">
            <Input
              label="PinClicks Max Records"
              type="number"
              value={pinclicksMaxRecords}
              onChange={(e) => setPinclicksMaxRecords(e.target.value)}
              placeholder="20"
            />
            <Input
              label="Winners Count"
              type="number"
              value={winnersCount}
              onChange={(e) => setWinnersCount(e.target.value)}
              placeholder="5"
            />
          </div>
        </div>

        <div className="border-t-[3px] border-base pt-5">
          <h3 className="text-sm font-black uppercase tracking-widest mb-4 text-muted">
            Publishing Configuration
          </h3>
          <div className="grid grid-cols-3 gap-5">
            <Select
              label="Publish Status"
              options={publishStatusOptions}
              value={publishStatus}
              onChange={(e) => setPublishStatus(e.target.value)}
              placeholder="Status"
            />
            <Input
              label="CSV Cadence (min)"
              type="number"
              value={csvCadenceMinutes}
              onChange={(e) => setCsvCadenceMinutes(e.target.value)}
              placeholder="240"
            />
            <Select
              label="Pin Template Mode"
              options={pinTemplateModeOptions}
              value={pinTemplateMode}
              onChange={(e) => setPinTemplateMode(e.target.value)}
              placeholder="Mode"
            />
          </div>
        </div>

        <div className="border-t-[3px] border-base pt-5">
          <h3 className="text-sm font-black uppercase tracking-widest mb-4 text-muted">
            Concurrency
          </h3>
          <div className="max-w-xs">
            <Input
              label="Max Concurrent Articles"
              type="number"
              value={maxConcurrentArticles}
              onChange={(e) => setMaxConcurrentArticles(e.target.value)}
              placeholder="3"
            />
          </div>
        </div>
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
            Pipeline config saved successfully
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
