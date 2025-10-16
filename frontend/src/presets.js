export const PRESETS = {
  "Encoder • Paragraph": {
    engine: "encoder",
    embed_model: "sentence-transformers/all-mpnet-base-v2",
    mlm_refiner: false,
    page_summarize: false,
    page_style: "paragraph",
  },
  "Qwen • Paragraph": {
    engine: "llm",
    ollama_text: "qwen2.5:7b-instruct",
    host: "",              // must be filled by user
    page_summarize: true,  // enabled only if host is provided
    page_style: "paragraph",
  },
  "Llama • Paragraph": {
    engine: "llm",
    ollama_text: "llama3.1:latest",
    host: "",
    page_summarize: true,
    page_style: "paragraph",
  },
};
