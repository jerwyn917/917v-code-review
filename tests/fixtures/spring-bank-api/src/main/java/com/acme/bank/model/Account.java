package com.acme.bank.model;

import jakarta.persistence.*;
import java.util.List;

@Entity
public class Account {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String owner;

    private String iban;

    private double balance;

    @OneToMany(mappedBy = "account", fetch = FetchType.EAGER)
    private List<Transaction> transactions;

    public Long getId() { return id; }
    public String getOwner() { return owner; }
    public String getIban() { return iban; }
    public double getBalance() { return balance; }
    public void setBalance(double balance) { this.balance = balance; }
    public List<Transaction> getTransactions() { return transactions; }
}
