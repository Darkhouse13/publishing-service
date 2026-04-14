// ---------------------------------------------------------------------------
// API client — fetch wrapper for /api/v1/... (proxied through Next.js rewrites)
// ---------------------------------------------------------------------------

import type {
  ApiError,
  Blog,
  BlogCreate,
  BlogUpdate,
  PipelineConfig,
  PipelineConfigUpdate,
  Run,
  RunCreate,
  Article,
  ArticleCreate,
  Credential,
  CredentialCreate,
} from './types';

// ---------------------------------------------------------------------------
// Generic fetch wrapper with error handling
// ---------------------------------------------------------------------------

class ApiClientError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(`API Error ${status}: ${detail}`);
    this.name = 'ApiClientError';
    this.status = status;
    this.detail = detail;
  }
}

async function fetchAPI<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `/api/v1${path}`;

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;

    try {
      const body = (await response.json()) as ApiError;
      if (body.detail) {
        detail = body.detail;
      }
    } catch {
      // Response body is not JSON — use default message
    }

    throw new ApiClientError(response.status, detail);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Blogs
// ---------------------------------------------------------------------------

export const blogsApi = {
  list(): Promise<Blog[]> {
    return fetchAPI<Blog[]>('/blogs');
  },

  get(id: string): Promise<Blog> {
    return fetchAPI<Blog>(`/blogs/${id}`);
  },

  create(data: BlogCreate): Promise<Blog> {
    return fetchAPI<Blog>('/blogs', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  update(id: string, data: BlogUpdate): Promise<Blog> {
    return fetchAPI<Blog>(`/blogs/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  patch(id: string, data: Partial<BlogUpdate>): Promise<Blog> {
    return fetchAPI<Blog>(`/blogs/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  delete(id: string): Promise<void> {
    return fetchAPI<void>(`/blogs/${id}`, {
      method: 'DELETE',
    });
  },
};

// ---------------------------------------------------------------------------
// Pipeline Config
// ---------------------------------------------------------------------------

export const pipelineConfigApi = {
  get(blogId: string): Promise<PipelineConfig> {
    return fetchAPI<PipelineConfig>(`/blogs/${blogId}/pipeline-config`);
  },

  update(blogId: string, data: PipelineConfigUpdate): Promise<PipelineConfig> {
    return fetchAPI<PipelineConfig>(`/blogs/${blogId}/pipeline-config`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },
};

// ---------------------------------------------------------------------------
// Runs
// ---------------------------------------------------------------------------

export const runsApi = {
  list(params?: { blog_id?: string; status?: string }): Promise<Run[]> {
    const searchParams = new URLSearchParams();
    if (params?.blog_id) searchParams.set('blog_id', params.blog_id);
    if (params?.status) searchParams.set('status', params.status);
    const query = searchParams.toString();
    return fetchAPI<Run[]>(`/runs${query ? `?${query}` : ''}`);
  },

  get(id: string): Promise<Run> {
    return fetchAPI<Run>(`/runs/${id}`);
  },

  create(data: RunCreate): Promise<Run> {
    return fetchAPI<Run>('/runs', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};

// ---------------------------------------------------------------------------
// Articles
// ---------------------------------------------------------------------------

export const articlesApi = {
  list(params?: { blog_id?: string; status?: string }): Promise<Article[]> {
    const searchParams = new URLSearchParams();
    if (params?.blog_id) searchParams.set('blog_id', params.blog_id);
    if (params?.status) searchParams.set('status', params.status);
    const query = searchParams.toString();
    return fetchAPI<Article[]>(`/articles${query ? `?${query}` : ''}`);
  },

  get(id: string): Promise<Article> {
    return fetchAPI<Article>(`/articles/${id}`);
  },

  create(data: ArticleCreate): Promise<Article> {
    return fetchAPI<Article>('/articles', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};

// ---------------------------------------------------------------------------
// Credentials
// ---------------------------------------------------------------------------

export const credentialsApi = {
  list(): Promise<Credential[]> {
    return fetchAPI<Credential[]>('/credentials');
  },

  create(data: CredentialCreate): Promise<Credential> {
    return fetchAPI<Credential>('/credentials', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  delete(id: string): Promise<void> {
    return fetchAPI<void>(`/credentials/${id}`, {
      method: 'DELETE',
    });
  },
};

// ---------------------------------------------------------------------------
// Export error class for consumer error handling
// ---------------------------------------------------------------------------

export { ApiClientError };
