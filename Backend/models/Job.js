const mongoose = require("mongoose");

const JobSchema = new mongoose.Schema(
  {
    // 🔗 Reference to recruiter (User)
    recruiter: {
      type: mongoose.Schema.Types.ObjectId,
      ref: "User",
      required: true,
    },

    // -------- Job details --------
    title: {
      type: String,
      required: true,
    },

    description: {
      type: String,
      default: "",
    },

    location: {
      type: String,
      default: "",
    },

    employmentType: {
      type: String,
      default: "",
    },

    salary: {
      min: { type: String, default: "" },
      max: { type: String, default: "" },
      currency: { type: String, default: "USD" },
    },

    skills: {
      type: [String],
      default: [],
    },

    aiQuestions: {
      type: [String],
      default: [],
    },

    status: {
      type: String,
      default: "Active",
    },
  },
  { timestamps: true }
);

module.exports = mongoose.model("Job", JobSchema);
