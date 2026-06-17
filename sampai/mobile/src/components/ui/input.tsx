import { TextInput, type TextInputProps } from 'react-native';

import { cn } from '@/lib/utils';

export function Input({ className, ...props }: TextInputProps & { className?: string }) {
  return (
    <TextInput
      placeholderTextColor="rgb(106 115 122)"
      className={cn(
        'rounded-lg border border-input bg-card px-3 py-3 text-base text-foreground',
        className,
      )}
      {...props}
    />
  );
}
