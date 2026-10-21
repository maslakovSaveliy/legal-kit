'use client';
import { useEffect } from 'react';

export default function Metrika() {
  useEffect(() => {
    // script loads from mc.yandex.ru
    (window as any).ym(12345678, 'init', { clickmap: true });
  }, []);
  return null;
}
