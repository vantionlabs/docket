import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** shadcn's class merger: conditional classes, with later Tailwind utilities winning. */
export function cn(...inputs: Array<ClassValue>) {
  return twMerge(clsx(inputs));
}
