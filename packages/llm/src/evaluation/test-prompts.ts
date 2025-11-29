/**
 * Test Prompts for LLM Evaluation
 *
 * A curated set of prompts for testing the LLM-backed builder pipeline
 */

export interface TestPrompt {
  id: string;
  category: string;
  prompt: string;
  expectedFeatures?: string[]; // Features that should appear in the result
  difficulty: 'simple' | 'medium' | 'complex';
}

/**
 * Test prompts organized by difficulty and category
 */
export const TEST_PROMPTS: TestPrompt[] = [
  // Simple prompts (clear requirements, minimal features)
  {
    id: 'simple-1',
    category: 'productivity',
    difficulty: 'simple',
    prompt: 'Build a todo list app with user authentication',
    expectedFeatures: ['auth', 'todos'],
  },
  {
    id: 'simple-2',
    category: 'social',
    difficulty: 'simple',
    prompt: 'Create a simple blog platform where users can post articles',
    expectedFeatures: ['auth', 'posts'],
  },
  {
    id: 'simple-3',
    category: 'e-commerce',
    difficulty: 'simple',
    prompt: 'Build a product catalog viewer with search functionality',
    expectedFeatures: ['products', 'search'],
  },

  // Medium prompts (moderate complexity, multiple features)
  {
    id: 'medium-1',
    category: 'productivity',
    difficulty: 'medium',
    prompt: 'Build a task management SaaS with user accounts, projects, tasks, and team collaboration',
    expectedFeatures: ['auth', 'projects', 'tasks', 'teams'],
  },
  {
    id: 'medium-2',
    category: 'social',
    difficulty: 'medium',
    prompt: 'Create a social bookmarking platform where users can save links, organize them into collections, and share publicly',
    expectedFeatures: ['auth', 'bookmarks', 'collections', 'sharing'],
  },
  {
    id: 'medium-3',
    category: 'e-commerce',
    difficulty: 'medium',
    prompt: 'Build an online store with product management, shopping cart, and Stripe payment integration',
    expectedFeatures: ['products', 'cart', 'billing', 'admin'],
  },
  {
    id: 'medium-4',
    category: 'education',
    difficulty: 'medium',
    prompt: 'Create a course platform where instructors can create courses, add lessons, and students can enroll',
    expectedFeatures: ['auth', 'courses', 'lessons', 'enrollment'],
  },
  {
    id: 'medium-5',
    category: 'entertainment',
    difficulty: 'medium',
    prompt: 'Build a movie watchlist app with ratings, reviews, and personalized recommendations',
    expectedFeatures: ['auth', 'movies', 'watchlist', 'ratings', 'reviews'],
  },

  // Complex prompts (detailed requirements, many features)
  {
    id: 'complex-1',
    category: 'productivity',
    difficulty: 'complex',
    prompt: 'Build a comprehensive project management SaaS with user authentication, team workspaces, projects, tasks with dependencies, time tracking, file attachments, comments, notifications, admin dashboard, and subscription billing with free and pro tiers',
    expectedFeatures: ['auth', 'workspaces', 'projects', 'tasks', 'time_tracking', 'files', 'comments', 'notifications', 'admin', 'billing'],
  },
  {
    id: 'complex-2',
    category: 'e-commerce',
    difficulty: 'complex',
    prompt: 'Create a multi-vendor marketplace where vendors can create stores, list products with variants and inventory, customers can browse, search, add to cart, checkout with Stripe, track orders, leave reviews, and admins can manage vendors and resolve disputes',
    expectedFeatures: ['auth', 'vendors', 'products', 'inventory', 'cart', 'billing', 'orders', 'reviews', 'admin'],
  },
  {
    id: 'complex-3',
    category: 'social',
    difficulty: 'complex',
    prompt: 'Build a community platform with user profiles, posts, comments, likes, followers, direct messaging, groups, events, notifications, moderation tools, and admin analytics dashboard',
    expectedFeatures: ['auth', 'profiles', 'posts', 'comments', 'likes', 'follows', 'messages', 'groups', 'events', 'notifications', 'moderation', 'admin'],
  },

  // Domain-specific prompts
  {
    id: 'devtools-1',
    category: 'dev-tools',
    difficulty: 'medium',
    prompt: 'Build a code snippet manager where developers can save, tag, and search code snippets with syntax highlighting',
    expectedFeatures: ['auth', 'snippets', 'tags', 'search'],
  },
  {
    id: 'iot-1',
    category: 'iot',
    difficulty: 'medium',
    prompt: 'Create a smart home dashboard that displays sensor data, controls devices, and shows historical trends',
    expectedFeatures: ['auth', 'sensors', 'devices', 'dashboard', 'history'],
  },
  {
    id: 'analytics-1',
    category: 'productivity',
    difficulty: 'medium',
    prompt: 'Build a personal habit tracker with daily check-ins, streak tracking, and progress visualization',
    expectedFeatures: ['auth', 'habits', 'check_ins', 'streaks', 'charts'],
  },

  // Edge cases (testing ambiguity handling)
  {
    id: 'edge-1',
    category: 'productivity',
    difficulty: 'medium',
    prompt: 'Build a SaaS for managing stuff',
    expectedFeatures: [], // Should trigger clarification
  },
  {
    id: 'edge-2',
    category: 'productivity',
    difficulty: 'simple',
    prompt: 'Note-taking app',
    expectedFeatures: ['notes'], // Minimal but valid
  },
];

/**
 * Get prompts by difficulty
 */
export function getPromptsByDifficulty(difficulty: 'simple' | 'medium' | 'complex'): TestPrompt[] {
  return TEST_PROMPTS.filter(p => p.difficulty === difficulty);
}

/**
 * Get prompts by category
 */
export function getPromptsByCategory(category: string): TestPrompt[] {
  return TEST_PROMPTS.filter(p => p.category === category);
}

/**
 * Get a specific prompt by ID
 */
export function getPromptById(id: string): TestPrompt | undefined {
  return TEST_PROMPTS.find(p => p.id === id);
}

/**
 * Get a random sample of N prompts
 */
export function getRandomSample(n: number): TestPrompt[] {
  const shuffled = [...TEST_PROMPTS].sort(() => Math.random() - 0.5);
  return shuffled.slice(0, Math.min(n, TEST_PROMPTS.length));
}
