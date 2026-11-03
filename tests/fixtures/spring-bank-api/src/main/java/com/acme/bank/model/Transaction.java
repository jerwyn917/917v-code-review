package com.acme.bank.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

@Entity
public class Transaction {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne
    private Account account;

    private double amount;

    private LocalDateTime createdAt = LocalDateTime.now();

    public Transaction() {}

    public Transaction(Account account, double amount) {
        this.account = account;
        this.amount = amount;
    }

    public double getAmount() { return amount; }
}
