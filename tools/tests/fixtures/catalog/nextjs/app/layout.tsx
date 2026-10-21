import type { ReactNode } from "react";
import Script from "next/script";
import { Inter } from "next/font/google";

const inter = Inter({ subsets: ["latin", "cyrillic"] });

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru">
      <body className={inter.className}>
        {children}
        <Script id="yandex-metrika" strategy="afterInteractive">{`
          (function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
          m[i].l=1*new Date();k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})
          (window, document, "script", "https://mc.yandex.ru/metrika/tag.js", "ym");
          ym(12345678, "init", { clickmap: true, trackLinks: true, accurateTrackBounce: true, webvisor: true });
        `}</Script>
        <noscript><div><img src="https://mc.yandex.ru/watch/12345678" style={{ position: "absolute", left: "-9999px" }} alt="" /></div></noscript>
      </body>
    </html>
  );
}
