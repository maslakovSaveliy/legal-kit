import { Pressable, Text } from 'react-native';
import { theme } from '../../src/theme';

export function Button({ title, onPress }: { title: string; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={{ backgroundColor: theme.colors.accent, padding: theme.spacing.md, borderRadius: theme.radius.md }}
    >
      <Text style={{ color: '#fff', textAlign: 'center' }}>{title}</Text>
    </Pressable>
  );
}
