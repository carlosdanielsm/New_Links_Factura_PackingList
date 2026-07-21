import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Proveedor IA",
  description: "Buscador asistido de productos y proveedores",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
