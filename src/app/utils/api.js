import OpenAI from 'openai';
import Anthropic from '@anthropic-ai/sdk';

export async function optimizePrompt(prompt, model) {
  const openaiKey = localStorage.getItem('openai_api_key');
  const anthropicKey = localStorage.getItem('anthropic_api_key');

  const systemPrompt = `You are an expert prompt engineer specializing in optimizing prompts for Large Language Models. Your task is to transform user prompts into highly effective, structured instructions that maximize model performance.

OBJECTIVE:
Transform the given prompt into a more effective version that:
1. Maximizes clarity and specificity
2. Includes necessary context and constraints
3. Uses precise, unambiguous language
4. Follows best practices for the specific model (GPT-4o/Claude 3.5)

PROMPT OPTIMIZATION RULES:
1. Structure: Break down complex tasks into clear, sequential steps
2. Context: Include relevant background information and desired outcome
3. Constraints: Specify any limitations, requirements, or preferences
4. Format: Use clear formatting with sections and bullet points when appropriate
5. Specificity: Replace vague terms with specific, measurable criteria
6. Output Format: Define the expected response format and style
7. Examples: Include examples when they would clarify the request

ADDITIONAL GUIDELINES:
- Maintain the original intent and core requirements
- Add clarifying details without changing the main objective
- Use consistent terminology throughout
- Include relevant domain-specific language
- Specify quality criteria and success metrics
- Add guardrails to prevent unwanted outputs

Original prompt: "${prompt}"

RESPONSE FORMAT:
Provide only the optimized prompt without explanations or meta-commentary. The optimized prompt should be immediately usable with the target model.`;

  try {
    if (model === 'gpt-4o') {
      if (!openaiKey) throw new Error('OpenAI API key not found');
      
      const openai = new OpenAI({
        apiKey: openaiKey,
        dangerouslyAllowBrowser: true
      });

      const response = await openai.chat.completions.create({
        model: 'gpt-4o',
        messages: [
          {
            role: 'system',
            content: 'You are an expert prompt engineer with deep knowledge of GPT-4o\'s capabilities and optimal interaction patterns. Your responses should be precisely formatted to maximize GPT-4o\'s understanding and performance.'
          },
          { role: 'user', content: systemPrompt }
        ],
        temperature: 0.4,
        max_tokens: 2000,
        top_p: 0.9,
        frequency_penalty: 0.3,
        presence_penalty: 0.1,
      });

      return response.choices[0].message.content;
    } else if (model === 'claude-3.5-sonnet') {
      if (!anthropicKey) throw new Error('Anthropic API key not found');

      const anthropic = new Anthropic({
        apiKey: anthropicKey,
      });

      const response = await anthropic.messages.create({
        model: 'claude-3.5-sonnet',
        system: 'You are an expert prompt engineer with deep knowledge of Claude\'s capabilities and optimal interaction patterns. Your responses should be precisely formatted to maximize Claude\'s understanding and performance.',
        messages: [
          { role: 'user', content: systemPrompt }
        ],
        temperature: 0.4,
        max_tokens: 2000,
        top_p: 0.9,
        top_k: 50,
      });

      return response.content[0].text;
    }
  } catch (error) {
    throw new Error(error.message || 'Failed to optimize prompt');
  }
} 