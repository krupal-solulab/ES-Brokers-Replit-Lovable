import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ArrowLeft, ArrowRight, CheckCircle2, Loader2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Form,
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormMessage,
} from "@/components/ui/form";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { simulateRequest } from "@/lib/simulate";

const FREE_EMAIL_DOMAINS = [
  "gmail.com",
  "yahoo.com",
  "hotmail.com",
  "outlook.com",
  "icloud.com",
  "aol.com",
];

const demoSchema = z.object({
  name: z.string().min(2, "Enter your full name"),
  workEmail: z
    .string()
    .min(1, "Work email is required")
    .email("Enter a valid email address")
    .refine(
      (v) => !FREE_EMAIL_DOMAINS.includes(v.split("@")[1]?.toLowerCase() ?? ""),
      "Please use your work email address",
    ),
  company: z.string().min(2, "Enter your company name"),
  role: z.string().min(1, "Select your role"),
  brokerType: z.string().min(1, "Select what best describes you"),
  submissionVolume: z.string().min(1, "Select your monthly submission volume"),
  message: z.string().max(1000, "Keep it under 1000 characters").optional(),
  // Honeypot — real users never see or fill this field. Any value here means
  // the submission is a bot and gets rejected before "sending" anything.
  website: z.string().max(0, "").optional(),
});
type DemoValues = z.infer<typeof demoSchema>;

type Status = "idle" | "loading" | "error" | "success";

export function DemoPage() {
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const form = useForm<DemoValues>({
    resolver: zodResolver(demoSchema),
    defaultValues: {
      name: "",
      workEmail: "",
      company: "",
      role: "",
      brokerType: "",
      submissionVolume: "",
      message: "",
      website: "",
    },
  });

  async function onSubmit(values: DemoValues) {
    if (values.website) return; // honeypot tripped — silently drop
    setStatus("loading");
    setErrorMsg("");
    try {
      // TODO: replace with a real POST to a server route (e.g.
      // src/routes/api.demo-request.ts) that sends via Resend/Web3Forms.
      // Nothing here is actually delivered to anyone yet.
      await simulateRequest(values);
      setStatus("success");
    } catch (err) {
      setStatus("error");
      setErrorMsg(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    }
  }

  if (status === "success") {
    return (
      <div className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center px-5 text-center animate-in fade-in-0 duration-500">
        <div className="grid h-14 w-14 place-items-center rounded-full bg-success/10">
          <CheckCircle2 className="h-7 w-7 text-success" />
        </div>
        <h1 className="mt-6 font-serif text-3xl tracking-[-0.01em]">Thanks — we'll be in touch.</h1>
        <p className="mt-3 text-ink-soft">
          Someone from our team will reach out within one business day to schedule a walkthrough of
          Submission Market Matching on your own book.
        </p>
        <Link
          to="/"
          className="mt-8 inline-flex items-center gap-2 text-sm font-medium text-foreground underline-offset-4 hover:underline"
        >
          <ArrowLeft className="h-4 w-4" /> Back to home
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto min-h-screen max-w-2xl px-5 py-16 md:py-24 animate-in fade-in-0 duration-500">
      <Link
        to="/"
        className="inline-flex items-center gap-2 text-sm text-ink-soft hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> Back to home
      </Link>

      <div className="mt-8">
        <div className="label-eyebrow">Book a demo</div>
        <h1 className="mt-4 font-serif text-4xl leading-[1.05] tracking-[-0.02em] md:text-5xl">
          See Coverline on your own submissions.
        </h1>
        <p className="mt-4 max-w-lg text-lg leading-relaxed text-ink-soft">
          Tell us a bit about your book. We'll tailor the walkthrough to your carrier panel and
          submission volume.
        </p>
      </div>

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="mt-10 space-y-5" noValidate>
          <div className="grid gap-5 sm:grid-cols-2">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Full name</FormLabel>
                  <FormControl>
                    <Input
                      autoComplete="name"
                      placeholder="Sam Delgado"
                      disabled={status === "loading"}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="workEmail"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Work email</FormLabel>
                  <FormControl>
                    <Input
                      type="email"
                      autoComplete="email"
                      placeholder="you@agency.com"
                      disabled={status === "loading"}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>

          <FormField
            control={form.control}
            name="company"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Company</FormLabel>
                <FormControl>
                  <Input
                    autoComplete="organization"
                    placeholder="Meridian Specialty Wholesale"
                    disabled={status === "loading"}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <div className="grid gap-5 sm:grid-cols-3">
            <FormField
              control={form.control}
              name="role"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Your role</FormLabel>
                  <Select
                    onValueChange={field.onChange}
                    value={field.value}
                    disabled={status === "loading"}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select role" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="broker">Wholesale broker</SelectItem>
                      <SelectItem value="principal">Principal / owner</SelectItem>
                      <SelectItem value="ops">Operations / support</SelectItem>
                      <SelectItem value="compliance">Compliance</SelectItem>
                      <SelectItem value="other">Other</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="brokerType"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>You are a</FormLabel>
                  <Select
                    onValueChange={field.onChange}
                    value={field.value}
                    disabled={status === "loading"}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select type" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="wholesale">Wholesale broker</SelectItem>
                      <SelectItem value="mga">MGA</SelectItem>
                      <SelectItem value="retail">Retail agency</SelectItem>
                      <SelectItem value="carrier">Carrier</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="submissionVolume"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Submissions / mo</FormLabel>
                  <Select
                    onValueChange={field.onChange}
                    value={field.value}
                    disabled={status === "loading"}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select volume" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="under-50">Under 50</SelectItem>
                      <SelectItem value="50-200">50 – 200</SelectItem>
                      <SelectItem value="200-500">200 – 500</SelectItem>
                      <SelectItem value="500-plus">500+</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>

          <FormField
            control={form.control}
            name="message"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Anything specific you want to see? (optional)</FormLabel>
                <FormControl>
                  <Textarea
                    rows={4}
                    placeholder="E.g. how carrier ranking works for habitational risk…"
                    disabled={status === "loading"}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* Honeypot — visually and semantically hidden from real users. */}
          <div
            className="absolute -left-[9999px] top-auto h-0 w-0 overflow-hidden"
            aria-hidden="true"
          >
            <label htmlFor="website">Website</label>
            <input
              id="website"
              type="text"
              tabIndex={-1}
              autoComplete="off"
              {...form.register("website")}
            />
          </div>

          {status === "error" && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              {errorMsg}
            </div>
          )}

          <Button
            type="submit"
            variant="brand"
            size="lg"
            className="w-full justify-center sm:w-auto"
            disabled={status === "loading"}
            aria-busy={status === "loading"}
          >
            {status === "loading" ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {status === "loading" ? "Sending…" : "Book a demo"}
            {status !== "loading" && <ArrowRight className="h-4 w-4" />}
          </Button>
        </form>
      </Form>
    </div>
  );
}
